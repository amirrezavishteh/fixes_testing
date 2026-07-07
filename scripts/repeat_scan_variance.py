#!/usr/bin/env python3
"""
repeat_scan_variance.py — measure scan-to-scan variance for a set of models.

The report flags that q averages fp16 probabilities over a batch with argmax
tie-breaking, so heads near the threshold (e.g. 0.877-0.888) might land on
either side of it between runs/GPUs — but this was never actually measured.
This harness re-invokes scripts/scan.py N times per model (each into its own
output dir) and reports the spread of q_score and the resulting flip rate in
the backdoor/not-backdoor decision at a given threshold.

This only re-scans EXISTING models already in the model zoo — it does not
train anything new.

Usage:
  python scripts/repeat_scan_variance.py \
      --model-zoo-dir /path/to/model_zoo --data-dir /path/to/data \
      --models id-W0051 id-W0052 id-W0075 id-W0077 id-W0048 \
      --repeats 5 --out-dir ./results/variance-check --threshold 0.90
"""
import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path


def run_one_scan(python_bin: str, scan_script: Path, model_zoo_dir: str, data_dir: str,
                  model_id: str, output_dir: Path, run_name: str, cache_dir: str) -> None:
    cmd = [
        python_bin, str(scan_script),
        "--model-zoo-dir", model_zoo_dir,
        "--data-dir", data_dir,
        "--output-dir", str(output_dir),
        "--run-name", run_name,
        "--model-id", model_id,
        "--cache-dir", cache_dir,
    ]
    print(f"  $ {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-scan the same models N times to measure q_score variance")
    parser.add_argument("--model-zoo-dir", required=True)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--models", nargs="+", required=True, help="Model IDs to repeat-scan (pick the ambiguous/near-threshold ones)")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--out-dir", required=True, help="Base directory; each repeat gets its own subdir")
    parser.add_argument("--cache-dir", default=".cache")
    parser.add_argument("--threshold", type=float, default=0.90)
    parser.add_argument("--python-bin", default=sys.executable)
    parser.add_argument("--scan-script", default=None, help="Path to scan.py (default: alongside this script)")
    args = parser.parse_args()

    scan_script = Path(args.scan_script) if args.scan_script else Path(__file__).parent / "scan.py"
    out_base = Path(args.out_dir)

    per_model_scores = {mid: [] for mid in args.models}

    for rep in range(1, args.repeats + 1):
        rep_dir = out_base / f"rep{rep:02d}"
        print(f"\n=== Repeat {rep}/{args.repeats} -> {rep_dir} ===")
        for model_id in args.models:
            run_one_scan(
                args.python_bin, scan_script, args.model_zoo_dir, args.data_dir,
                model_id, rep_dir, run_name=f"variance-rep{rep}", cache_dir=args.cache_dir,
            )
            result_path = rep_dir / model_id / "result.json"
            if result_path.exists():
                q = json.loads(result_path.read_text()).get("q_score")
                if q is not None:
                    per_model_scores[model_id].append(float(q))
                    print(f"    {model_id}: q_score = {q:.4f}")
            else:
                print(f"    {model_id}: WARNING — no result.json produced")

    print("\n" + "=" * 70)
    print(f"Variance summary over {args.repeats} repeats (threshold={args.threshold})")
    print("=" * 70)
    for model_id, scores in per_model_scores.items():
        if len(scores) < 2:
            print(f"{model_id}: fewer than 2 successful repeats — skipping stats")
            continue
        mean = statistics.mean(scores)
        stdev = statistics.stdev(scores)
        decisions = [s > args.threshold for s in scores]
        flips = len(set(decisions)) > 1
        print(
            f"{model_id:>12}  n={len(scores)}  mean={mean:.4f}  stdev={stdev:.4f}  "
            f"range=[{min(scores):.4f}, {max(scores):.4f}]  "
            f"decision_flips_across_repeats={'YES' if flips else 'no'}"
        )

    print(
        "\nAny model with decision_flips_across_repeats=YES means its is_backdoor label "
        "is not stable at this threshold under re-run/hardware noise alone — treat its "
        "single-run label in the main report as provisional."
    )


if __name__ == "__main__":
    main()
