#!/usr/bin/env python3
"""
results_to_csv.py — flatten a scan run directory into one CSV of the key info.

Reads each <run-dir>/<id-*>/{result.json, arguments.json} and writes a CSV with
the ground truth + BAIT output per model, plus a short summary to stdout.

Usage:
  python scripts/results_to_csv.py --run-dir ./results/baseline-original
  python scripts/results_to_csv.py --run-dir ./results/baseline-original --out my.csv
"""
import argparse
import csv
import json
import os
from pathlib import Path

FIELDS = (
    "model_id", "base_model", "attack", "gt_is_backdoor", "pred_is_backdoor",
    "q_score", "trigger", "target", "invert_target", "time_taken_s",
)


def row_for(mdir: Path, model_id: str) -> dict:
    """Build one CSV row from a single model's result.json + arguments.json."""
    row = {field: "" for field in FIELDS}
    row["model_id"] = model_id

    result_path = mdir / "result.json"
    args_path = mdir / "arguments.json"

    if args_path.exists():
        try:
            args = json.loads(args_path.read_text())
        except Exception:
            args = {}
        model_args = args.get("model_args", {})
        row["base_model"] = model_args.get("base_model", "")
        row["attack"] = model_args.get("attack", "")
        row["gt_is_backdoor"] = model_args.get("is_backdoor", "")
        row["trigger"] = model_args.get("trigger", "")
        row["target"] = model_args.get("target", "")

    if result_path.exists():
        try:
            result = json.loads(result_path.read_text())
        except Exception:
            result = {}
        row["pred_is_backdoor"] = result.get("is_backdoor", "")
        row["q_score"] = result.get("q_score", "")
        row["invert_target"] = result.get("invert_target", "")
        row["time_taken_s"] = result.get("time_taken", "")

    return row


def main() -> None:
    parser = argparse.ArgumentParser(description="Flatten a BAIT scan run directory into a CSV")
    parser.add_argument("--run-dir", required=True, help="Directory containing one subdir per scanned model id")
    parser.add_argument("--out", default=None, help="Output CSV path (default: <run-dir>/scan_results.csv)")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    out_path = Path(args.out) if args.out else run_dir / "scan_results.csv"

    model_dirs = sorted(
        p for p in run_dir.iterdir()
        if p.is_dir() and (p / "arguments.json").exists()
    )

    rows = [row_for(mdir, mdir.name) for mdir in model_dirs]

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(FIELDS))
        writer.writeheader()
        writer.writerows(rows)

    n_done = sum(1 for r in rows if r["pred_is_backdoor"] != "")
    n_missing = len(rows) - n_done
    print(f"Wrote {len(rows)} rows to {out_path}")
    print(f"  with result.json : {n_done}")
    print(f"  missing result   : {n_missing}")


if __name__ == "__main__":
    main()
