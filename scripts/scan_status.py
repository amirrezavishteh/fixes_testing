#!/usr/bin/env python3
"""
scan_status.py — show which models are done / pending / failed for a scan run.

Compares the id-* model dirs in the zoo against the result.json files in a run
directory, so you can see what's left and resume. The scan itself already skips
any model that has a result.json, so to CONTINUE you just re-run the same
bait-scan command — it picks up the pending + previously-failed models.

  done    : has result.json
  failed  : run dir exists with arguments.json but no result.json (crashed mid-scan)
  pending : never started (no run subdir)

Usage:
  python scripts/scan_status.py \
      --model-zoo-dir /media/.../bait-sparsemax-zoo/models \
      --run-dir ./results/baseline-original
"""
import argparse
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Show done/pending/failed models for a BAIT scan run")
    parser.add_argument("--model-zoo-dir", required=True, help="Directory containing one subdir per model id (id-*)")
    parser.add_argument("--run-dir", required=True, help="Scan run/output directory")
    parser.add_argument("--verbose", action="store_true", help="List every model id in each bucket")
    args = parser.parse_args()

    zoo_dir = Path(args.model_zoo_dir)
    run_dir = Path(args.run_dir)

    all_ids = sorted(p.name for p in zoo_dir.iterdir() if p.is_dir())

    done, failed, pending = [], [], []
    for model_id in all_ids:
        mdir = run_dir / model_id
        result_path = mdir / "result.json"
        args_path = mdir / "arguments.json"

        if result_path.exists():
            done.append(model_id)
        elif args_path.exists():
            failed.append(model_id)
        else:
            pending.append(model_id)

    print(f"Model zoo : {zoo_dir}  ({len(all_ids)} models)")
    print(f"Run dir   : {run_dir}")
    print(f"  done    : {len(done)}")
    print(f"  failed  : {len(failed)}  (crashed mid-scan — has arguments.json but no result.json)")
    print(f"  pending : {len(pending)} (never started)")

    if args.verbose:
        for label, ids in (("done", done), ("failed", failed), ("pending", pending)):
            if ids:
                print(f"\n{label}:")
                for model_id in ids:
                    print(f"  {model_id}")

    if failed or pending:
        print(
            "\nTo resume: re-run the same bait-scan command with the same --output-dir. "
            "Models with a result.json are skipped automatically."
        )


if __name__ == "__main__":
    main()
