import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sklearn.model_selection import GroupShuffleSplit

from simulator.generator import HIDDEN_FIELDS, VISIBLE_FIELDS

IDENTIFIER_FIELDS = frozenset({"case_id", "customer_id", "payment_id"})
NUMERIC_FIELDS = (
    "amount",
    "attempt_count",
    "case_age_days",
    "customer_tenure_days",
    "prior_successes",
    "prior_failures",
    "engagement_score",
)
CATEGORICAL_FIELDS = (
    "currency",
    "failure_reason",
    "failure_source",
    "payment_method",
    "available_methods",
)
MODEL_FIELDS = NUMERIC_FIELDS + CATEGORICAL_FIELDS

ACTION_TARGETS = {
    "NO_INTERVENTION": "would_recover_without_intervention",
    "RECOVERY_LINK": "would_recover_with_recovery_link",
    "UPDATE_PROMPT": "would_recover_with_update_prompt",
    "DELAY": "would_recover_after_delay",
}

ACTION_PROBABILITY_FIELDS = {
    "NO_INTERVENTION": "p_without_intervention",
    "RECOVERY_LINK": "p_recovery_link",
    "UPDATE_PROMPT": "p_update_prompt",
    "DELAY": "p_delay",
}


class DatasetValidationError(ValueError):
    pass


@dataclass(frozen=True)
class DatasetSplit:
    train: np.ndarray
    validation: np.ndarray
    test: np.ndarray


@dataclass(frozen=True)
class TrainingDataset:
    visible_rows: list[dict[str, str]]
    hidden_rows: list[dict[str, str]]
    manifest: dict

    @classmethod
    def load(cls, dataset_dir: Path) -> "TrainingDataset":
        manifest_path = dataset_dir / "manifest.json"
        if not manifest_path.exists():
            raise DatasetValidationError("Dataset manifest is missing.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        visible_path = dataset_dir / manifest["features"]["file"]
        hidden_path = dataset_dir / manifest["ground_truth"]["file"]
        cls._verify_hash(visible_path, manifest["features"]["sha256"])
        cls._verify_hash(hidden_path, manifest["ground_truth"]["sha256"])
        visible_rows, visible_fields = cls._read_csv(visible_path)
        hidden_rows, hidden_fields = cls._read_csv(hidden_path)

        if tuple(visible_fields) != VISIBLE_FIELDS:
            raise DatasetValidationError("Visible feature schema is not supported.")
        if tuple(hidden_fields) != HIDDEN_FIELDS:
            raise DatasetValidationError("Hidden ground-truth schema is not supported.")
        if set(visible_fields) & set(hidden_fields) != {"case_id"}:
            raise DatasetValidationError("Visible and hidden schemas overlap.")
        if len(visible_rows) != len(hidden_rows) or not visible_rows:
            raise DatasetValidationError("Visible and hidden row counts must match.")
        visible_ids = [row["case_id"] for row in visible_rows]
        hidden_ids = [row["case_id"] for row in hidden_rows]
        if visible_ids != hidden_ids or len(set(visible_ids)) != len(visible_ids):
            raise DatasetValidationError("Case IDs must be unique and aligned.")
        if manifest.get("case_count") != len(visible_rows):
            raise DatasetValidationError("Manifest case count does not match data.")
        return cls(visible_rows, hidden_rows, manifest)

    def features(self, indices: np.ndarray | None = None) -> np.ndarray:
        selected = self.visible_rows if indices is None else [self.visible_rows[i] for i in indices]
        return np.asarray(
            [
                [self._feature_value(row, field) for field in MODEL_FIELDS]
                for row in selected
            ],
            dtype=object,
        )

    def labels(self, action: str, indices: np.ndarray) -> np.ndarray:
        field = ACTION_TARGETS[action]
        return np.asarray([int(self.hidden_rows[i][field]) for i in indices])

    def outcome_matrix(self, indices: np.ndarray) -> np.ndarray:
        return np.column_stack(
            [self.labels(action, indices) for action in ACTION_TARGETS]
        )

    def probability_matrix(self, indices: np.ndarray) -> np.ndarray:
        return np.column_stack(
            [
                np.asarray(
                    [
                        float(self.hidden_rows[i][ACTION_PROBABILITY_FIELDS[action]])
                        for i in indices
                    ]
                )
                for action in ACTION_TARGETS
            ]
        )

    def split(self, seed: int) -> DatasetSplit:
        indices = np.arange(len(self.visible_rows))
        groups = np.asarray([row["customer_id"] for row in self.visible_rows])
        first = GroupShuffleSplit(n_splits=1, test_size=0.30, random_state=seed)
        train, remainder = next(first.split(indices, groups=groups))
        second = GroupShuffleSplit(n_splits=1, test_size=0.50, random_state=seed + 1)
        validation_relative, test_relative = next(
            second.split(remainder, groups=groups[remainder])
        )
        validation = remainder[validation_relative]
        test = remainder[test_relative]
        self._assert_group_isolation(groups, train, validation, test)
        return DatasetSplit(train=train, validation=validation, test=test)

    @staticmethod
    def _feature_value(row: dict[str, str], field: str):
        if field in NUMERIC_FIELDS:
            return float(row[field])
        return row[field]

    @staticmethod
    def _read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return list(reader), list(reader.fieldnames or [])

    @staticmethod
    def _verify_hash(path: Path, expected: str) -> None:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected:
            raise DatasetValidationError(f"Checksum mismatch for {path.name}.")

    @staticmethod
    def _assert_group_isolation(groups, train, validation, test) -> None:
        group_sets = [set(groups[indices]) for indices in (train, validation, test)]
        if any(
            group_sets[left] & group_sets[right]
            for left, right in ((0, 1), (0, 2), (1, 2))
        ):
            raise DatasetValidationError("Customer groups overlap across splits.")
