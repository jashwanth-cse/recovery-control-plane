import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from ml.artifact import ActionConditionalModel
from ml.dataset import (
    ACTION_TARGETS,
    CATEGORICAL_FIELDS,
    MODEL_FIELDS,
    NUMERIC_FIELDS,
    DatasetSplit,
    TrainingDataset,
)

MODEL_FAMILY = "calibrated-gradient-boosting"
TRANSIENT_SOURCES = frozenset({"bank", "gateway"})
TRANSIENT_REASONS = frozenset(
    {"bank_error", "payment_failed", "payment_timed_out"}
)


@dataclass(frozen=True)
class TrainingConfig:
    seed: int = 42
    max_iter: int = 120
    calibration_folds: int = 3

    def validate(self) -> None:
        if self.max_iter < 10:
            raise ValueError("max_iter must be at least 10")
        if self.calibration_folds < 2:
            raise ValueError("calibration_folds must be at least 2")


def train_action_models(
    dataset_dir: Path,
    output_dir: Path,
    config: TrainingConfig,
) -> dict[str, Any]:
    config.validate()
    dataset = TrainingDataset.load(dataset_dir)
    split = dataset.split(config.seed)
    version = _model_version(dataset, config)
    estimators = {}
    metrics = {"validation": {}, "test": {}}

    train_features = dataset.features(split.train)
    validation_features = dataset.features(split.validation)
    test_features = dataset.features(split.test)
    for action in ACTION_TARGETS:
        estimator = _estimator(config)
        estimator.fit(train_features, dataset.labels(action, split.train))
        estimators[action] = estimator
        metrics["validation"][action] = _metrics(
            dataset.labels(action, split.validation),
            estimator.predict_proba(validation_features)[:, 1],
        )
        metrics["test"][action] = _metrics(
            dataset.labels(action, split.test),
            estimator.predict_proba(test_features)[:, 1],
        )

    model = ActionConditionalModel(version=version, estimators=estimators)
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / "model.joblib"
    model.save(model_path)
    comparison = _compare_with_rule_baseline(dataset, split, model, test_features)
    metadata = {
        "model_version": version,
        "model_family": MODEL_FAMILY,
        "seed": config.seed,
        "feature_fields": list(MODEL_FIELDS),
        "action_targets": ACTION_TARGETS,
        "dataset": {
            "simulator_version": dataset.manifest["simulator_version"],
            "case_count": dataset.manifest["case_count"],
            "feature_sha256": dataset.manifest["features"]["sha256"],
            "ground_truth_sha256": dataset.manifest["ground_truth"]["sha256"],
        },
        "splits": _split_metadata(dataset, split),
        "metrics": metrics,
        "rule_baseline_comparison": comparison,
        "artifact": {
            "file": model_path.name,
            "sha256": _sha256(model_path),
        },
    }
    _write_json(output_dir / "metadata.json", metadata)
    return metadata


def _estimator(config: TrainingConfig) -> CalibratedClassifierCV:
    numeric_indices = list(range(len(NUMERIC_FIELDS)))
    categorical_indices = list(
        range(len(NUMERIC_FIELDS), len(NUMERIC_FIELDS) + len(CATEGORICAL_FIELDS))
    )
    preprocessor = ColumnTransformer(
        [
            ("numeric", "passthrough", numeric_indices),
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                categorical_indices,
            ),
        ]
    )
    pipeline = Pipeline(
        [
            ("features", preprocessor),
            (
                "classifier",
                GradientBoostingClassifier(
                    learning_rate=0.08,
                    n_estimators=config.max_iter,
                    max_depth=3,
                    min_samples_leaf=20,
                    random_state=config.seed,
                ),
            ),
        ]
    )
    return CalibratedClassifierCV(
        estimator=pipeline,
        method="sigmoid",
        cv=config.calibration_folds,
        n_jobs=1,
    )


def _metrics(labels: np.ndarray, probabilities: np.ndarray) -> dict[str, float]:
    return {
        "roc_auc": float(roc_auc_score(labels, probabilities)),
        "pr_auc": float(average_precision_score(labels, probabilities)),
        "brier_score": float(brier_score_loss(labels, probabilities)),
        "log_loss": float(log_loss(labels, probabilities, labels=[0, 1])),
        "expected_calibration_error": _expected_calibration_error(
            labels, probabilities
        ),
        "positive_rate": float(np.mean(labels)),
    }


def _expected_calibration_error(
    labels: np.ndarray, probabilities: np.ndarray, bins: int = 10
) -> float:
    boundaries = np.linspace(0, 1, bins + 1)
    total = len(labels)
    error = 0.0
    for index in range(bins):
        lower, upper = boundaries[index], boundaries[index + 1]
        mask = (probabilities >= lower) & (
            probabilities <= upper if index == bins - 1 else probabilities < upper
        )
        if np.any(mask):
            error += float(np.mean(mask)) * abs(
                float(np.mean(labels[mask])) - float(np.mean(probabilities[mask]))
            )
    return error if total else 0.0


def _compare_with_rule_baseline(
    dataset: TrainingDataset,
    split: DatasetSplit,
    model: ActionConditionalModel,
    test_features: np.ndarray,
) -> dict[str, Any]:
    actions = list(ACTION_TARGETS)
    predictions = model.predict_matrix(test_features)
    prediction_matrix = np.column_stack([predictions[action] for action in actions])
    ai_choices = np.argmax(prediction_matrix, axis=1)
    outcomes = dataset.outcome_matrix(split.test)
    latent_probabilities = dataset.probability_matrix(split.test)
    oracle_choices = np.argmax(latent_probabilities, axis=1)
    rule_choices = np.asarray(
        [
            actions.index("RECOVERY_LINK")
            if (
                dataset.visible_rows[row_index]["failure_source"]
                in TRANSIENT_SOURCES
                or dataset.visible_rows[row_index]["failure_reason"]
                in TRANSIENT_REASONS
            )
            else actions.index("NO_INTERVENTION")
            for row_index in split.test
        ]
    )
    row_indices = np.arange(len(split.test))
    ai_rate = float(np.mean(outcomes[row_indices, ai_choices]))
    rule_rate = float(np.mean(outcomes[row_indices, rule_choices]))
    oracle_rate = float(np.mean(outcomes[row_indices, oracle_choices]))
    return {
        "test_cases": len(split.test),
        "ai_recovery_rate": ai_rate,
        "rule_recovery_rate": rule_rate,
        "absolute_rate_lift": ai_rate - rule_rate,
        "oracle_recovery_rate": oracle_rate,
        "action_selection_accuracy": float(np.mean(ai_choices == oracle_choices)),
        "outperformed_rule_baseline": ai_rate > rule_rate,
    }


def _split_metadata(dataset: TrainingDataset, split: DatasetSplit) -> dict[str, Any]:
    groups = np.asarray([row["customer_id"] for row in dataset.visible_rows])
    return {
        name: {
            "rows": len(indices),
            "customers": len(set(groups[indices])),
        }
        for name, indices in (
            ("train", split.train),
            ("validation", split.validation),
            ("test", split.test),
        )
    }


def _model_version(dataset: TrainingDataset, config: TrainingConfig) -> str:
    identity = json.dumps(
        {
            "family": MODEL_FAMILY,
            "features": dataset.manifest["features"]["sha256"],
            "ground_truth": dataset.manifest["ground_truth"]["sha256"],
            "seed": config.seed,
            "max_iter": config.max_iter,
            "calibration_folds": config.calibration_folds,
        },
        sort_keys=True,
    )
    return f"action-gbdt-{hashlib.sha256(identity.encode()).hexdigest()[:12]}"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
