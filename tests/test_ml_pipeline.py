import csv
import hashlib
import json

import numpy as np
import pytest

from ml import ActionConditionalModel
from ml.dataset import DatasetValidationError, TrainingDataset
from ml.inference import predict_file
from ml.training import TrainingConfig, train_action_models
from simulator import SimulationConfig, SyntheticDatasetGenerator


@pytest.fixture(scope="module")
def trained_model(tmp_path_factory):
    root = tmp_path_factory.mktemp("phase8-model")
    dataset_dir = root / "dataset"
    model_dir = root / "model"
    SyntheticDatasetGenerator(
        SimulationConfig(case_count=1800, seed=808)
    ).generate(dataset_dir)
    metadata = train_action_models(
        dataset_dir,
        model_dir,
        TrainingConfig(seed=808, max_iter=25),
    )
    return dataset_dir, model_dir, metadata


def test_training_uses_customer_isolated_splits_and_visible_features_only(
    trained_model,
):
    dataset_dir, _, metadata = trained_model
    dataset = TrainingDataset.load(dataset_dir)
    split = dataset.split(808)
    groups = np.asarray([row["customer_id"] for row in dataset.visible_rows])

    train_groups = set(groups[split.train])
    validation_groups = set(groups[split.validation])
    test_groups = set(groups[split.test])
    assert not train_groups & validation_groups
    assert not train_groups & test_groups
    assert not validation_groups & test_groups
    assert not any(
        field.startswith("would_recover") or field.startswith("p_")
        for field in metadata["feature_fields"]
    )
    assert sum(part["rows"] for part in metadata["splits"].values()) == 1800


def test_action_models_are_calibrated_versioned_and_round_trip(trained_model):
    dataset_dir, model_dir, metadata = trained_model
    model_path = model_dir / "model.joblib"
    model = ActionConditionalModel.load(model_path)
    dataset = TrainingDataset.load(dataset_dir)
    rows = dataset.visible_rows[:12]
    predictions = model.predict_rows(rows)

    assert model.version == metadata["model_version"]
    assert metadata["model_family"] == "calibrated-gradient-boosting"
    assert set(predictions[0]) == {
        "NO_INTERVENTION",
        "RECOVERY_LINK",
        "UPDATE_PROMPT",
        "DELAY",
    }
    assert all(0 <= value <= 1 for row in predictions for value in row.values())
    assert any(len(set(row.values())) > 1 for row in predictions)
    assert metadata["artifact"]["sha256"] == hashlib.sha256(
        model_path.read_bytes()
    ).hexdigest()
    for split_name in ("validation", "test"):
        for action_metrics in metadata["metrics"][split_name].values():
            assert 0 <= action_metrics["roc_auc"] <= 1
            assert 0 <= action_metrics["pr_auc"] <= 1
            assert 0 <= action_metrics["brier_score"] <= 1
            assert 0 <= action_metrics["expected_calibration_error"] <= 1


def test_inference_writes_only_case_ids_and_action_probabilities(
    trained_model, tmp_path
):
    dataset_dir, model_dir, _ = trained_model
    output_path = tmp_path / "predictions.csv"
    count = predict_file(
        model_dir / "model.joblib",
        dataset_dir / "features.csv",
        output_path,
    )

    with output_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert count == len(rows) == 1800
    assert tuple(rows[0]) == (
        "case_id",
        "p_no_intervention",
        "p_recovery_link",
        "p_update_prompt",
        "p_delay",
    )
    assert not any("would_recover" in field for field in rows[0])


def test_loader_rejects_hidden_column_leakage(tmp_path):
    dataset_dir = tmp_path / "leaky"
    manifest = SyntheticDatasetGenerator(
        SimulationConfig(case_count=50, seed=81)
    ).generate(dataset_dir)
    features_path = dataset_dir / "features.csv"
    lines = features_path.read_text(encoding="utf-8").splitlines()
    lines[0] += ",would_recover_without_intervention"
    for index in range(1, len(lines)):
        lines[index] += ",0"
    features_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest["features"]["sha256"] = hashlib.sha256(
        features_path.read_bytes()
    ).hexdigest()
    (dataset_dir / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    with pytest.raises(DatasetValidationError, match="schema"):
        TrainingDataset.load(dataset_dir)
