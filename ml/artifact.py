from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from ml.dataset import ACTION_TARGETS, MODEL_FIELDS, NUMERIC_FIELDS


@dataclass
class ActionConditionalModel:
    version: str
    estimators: dict[str, Any]
    feature_fields: tuple[str, ...] = MODEL_FIELDS

    def predict_matrix(self, features: np.ndarray) -> dict[str, np.ndarray]:
        return {
            action: estimator.predict_proba(features)[:, 1]
            for action, estimator in self.estimators.items()
        }

    def predict_rows(self, rows: list[dict[str, str]]) -> list[dict[str, float]]:
        features = np.asarray(
            [
                [
                    float(row[field]) if field in NUMERIC_FIELDS else row[field]
                    for field in self.feature_fields
                ]
                for row in rows
            ],
            dtype=object,
        )
        predictions = self.predict_matrix(features)
        return [
            {action: float(predictions[action][index]) for action in ACTION_TARGETS}
            for index in range(len(rows))
        ]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        joblib.dump(self, temporary)
        temporary.replace(path)

    @classmethod
    def load(cls, path: Path) -> "ActionConditionalModel":
        loaded = joblib.load(path)
        if not isinstance(loaded, cls):
            raise TypeError("Artifact is not an action-conditional model.")
        return loaded
