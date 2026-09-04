import argparse
import csv
from pathlib import Path

from ml.artifact import ActionConditionalModel
from simulator.generator import VISIBLE_FIELDS


def predict_file(model_path: Path, input_path: Path, output_path: Path) -> int:
    with input_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != VISIBLE_FIELDS:
            raise ValueError("Inference input does not match the visible feature schema.")
        rows = list(reader)
    model = ActionConditionalModel.load(model_path)
    predictions = model.predict_rows(rows)
    fields = ["case_id"] + [f"p_{action.lower()}" for action in model.estimators]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row, prediction in zip(rows, predictions):
            output = {"case_id": row["case_id"]}
            output.update(
                {
                    f"p_{action.lower()}": f"{probability:.8f}"
                    for action, probability in prediction.items()
                }
            )
            writer.writerow(output)
    temporary.replace(output_path)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run recovery model inference.")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    count = predict_file(arguments.model, arguments.input, arguments.output)
    print(f"wrote {count} predictions to {arguments.output}")


if __name__ == "__main__":
    main()
