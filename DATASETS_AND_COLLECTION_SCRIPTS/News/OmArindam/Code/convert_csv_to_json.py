import argparse
import csv
import json
from pathlib import Path


def convert_csv(csv_path: Path) -> Path:
    json_path = csv_path.with_suffix(".json")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if not reader.fieldnames:
            raise ValueError(f"{csv_path}: missing CSV header")

        rows = []
        for line_number, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(
                    f"{csv_path}: inconsistent number of columns on line {line_number}"
                )
            rows.append(row)

    with json_path.open("w", encoding="utf-8", newline="\n") as json_file:
        json.dump(rows, json_file, ensure_ascii=False, indent=2)
        json_file.write("\n")

    return json_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert every CSV file in a directory to a JSON array."
    )
    parser.add_argument(
        "directory",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="directory containing CSV files (defaults to this script's directory)",
    )
    args = parser.parse_args()

    csv_files = sorted(args.directory.glob("*.csv"))
    if not csv_files:
        print(f"No CSV files found in {args.directory}")
        return

    for csv_path in csv_files:
        json_path = convert_csv(csv_path)
        print(f"Converted {csv_path.name} -> {json_path.name}")


if __name__ == "__main__":
    main()
