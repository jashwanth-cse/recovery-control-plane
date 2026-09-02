import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from simulator import SimulationConfig, SyntheticDatasetGenerator
from simulator.generator import HIDDEN_FIELDS, VISIBLE_FIELDS


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_thousands_scale_dataset_is_reproducible_and_ground_truth_is_separate(
    tmp_path,
):
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    config = SimulationConfig(case_count=2500, seed=20260902)

    first_manifest = SyntheticDatasetGenerator(config).generate(first_dir)
    second_manifest = SyntheticDatasetGenerator(config).generate(second_dir)

    for filename in ("features.csv", "ground_truth.csv", "manifest.json"):
        assert (first_dir / filename).read_bytes() == (second_dir / filename).read_bytes()
    assert first_manifest == second_manifest

    visible = read_rows(first_dir / "features.csv")
    hidden = read_rows(first_dir / "ground_truth.csv")
    assert len(visible) == len(hidden) == 2500
    assert tuple(visible[0]) == VISIBLE_FIELDS
    assert tuple(hidden[0]) == HIDDEN_FIELDS
    assert set(VISIBLE_FIELDS) & set(HIDDEN_FIELDS) == {"case_id"}
    assert [row["case_id"] for row in visible] == [row["case_id"] for row in hidden]
    assert not any(
        "recover" in field or field.startswith("p_") for field in VISIBLE_FIELDS
    )

    assert first_manifest["features"]["sha256"] == sha256(
        first_dir / "features.csv"
    )
    assert first_manifest["ground_truth"]["sha256"] == sha256(
        first_dir / "ground_truth.csv"
    )
    assert first_manifest["ground_truth"]["access"] == "evaluation_only"


def test_generator_produces_varied_observed_and_counterfactual_data(tmp_path):
    output_dir = tmp_path / "variation"
    SyntheticDatasetGenerator(
        SimulationConfig(case_count=3000, seed=73)
    ).generate(output_dir)
    visible = read_rows(output_dir / "features.csv")
    hidden = read_rows(output_dir / "ground_truth.csv")

    assert len({row["customer_id"] for row in visible}) > 500
    assert len({row["failure_reason"] for row in visible}) == 6
    assert len({row["payment_method"] for row in visible}) == 4
    assert len({row["case_age_days"] for row in visible}) == 14
    assert len({row["amount"] for row in visible}) > 100
    assert any(int(row["prior_successes"]) > 0 for row in visible)
    assert any(int(row["prior_failures"]) > 0 for row in visible)

    for field in HIDDEN_FIELDS[1:5]:
        assert {row[field] for row in hidden} == {"0", "1"}
    without = sum(
        int(row["would_recover_without_intervention"]) for row in hidden
    )
    with_link = sum(
        int(row["would_recover_with_recovery_link"]) for row in hidden
    )
    assert with_link > without


def test_different_seed_changes_dataset(tmp_path):
    first = tmp_path / "seed-one"
    second = tmp_path / "seed-two"
    SyntheticDatasetGenerator(SimulationConfig(case_count=100, seed=1)).generate(first)
    SyntheticDatasetGenerator(SimulationConfig(case_count=100, seed=2)).generate(second)
    assert (first / "features.csv").read_bytes() != (
        second / "features.csv"
    ).read_bytes()


def test_cli_generates_dataset_with_one_command(tmp_path):
    output_dir = tmp_path / "cli"
    repository_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "simulator",
            "--cases",
            "1200",
            "--seed",
            "19",
            "--output-dir",
            str(output_dir),
        ],
        cwd=repository_root,
        capture_output=True,
        check=True,
        text=True,
    )

    output_manifest = json.loads(result.stdout)
    stored_manifest = json.loads((output_dir / "manifest.json").read_text())
    assert output_manifest == stored_manifest
    assert stored_manifest["case_count"] == 1200
    with (output_dir / "features.csv").open() as handle:
        assert sum(1 for _ in handle) == 1201
