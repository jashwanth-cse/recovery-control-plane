import argparse
import json
from pathlib import Path

from simulator.generator import SimulationConfig, SyntheticDatasetGenerator


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate deterministic synthetic revenue-recovery data."
    )
    parser.add_argument("--cases", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/simulator"),
    )
    arguments = parser.parse_args()
    manifest = SyntheticDatasetGenerator(
        SimulationConfig(case_count=arguments.cases, seed=arguments.seed)
    ).generate(arguments.output_dir)
    print(json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
