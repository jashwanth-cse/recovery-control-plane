import argparse
import json
from pathlib import Path

from ml.training import TrainingConfig, train_action_models


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train calibrated action-conditional recovery models."
    )
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/model"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-iter", type=int, default=120)
    arguments = parser.parse_args()
    metadata = train_action_models(
        arguments.dataset_dir,
        arguments.output_dir,
        TrainingConfig(seed=arguments.seed, max_iter=arguments.max_iter),
    )
    print(json.dumps(metadata, sort_keys=True))


if __name__ == "__main__":
    main()
