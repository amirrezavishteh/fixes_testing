#!/usr/bin/env python3
"""
rethreshold.py — compare detection results across Q-SCORE thresholds.

The BAIT decision is simply `is_backdoor = q_score > threshold`. The q_score is
already computed and saved in each result.json, so changing the threshold does
NOT require re-scanning. This tool re-applies any set of thresholds to a finished
(or in-progress) run directory and prints TPR / FPR / accuracy at each, so you can
see exactly how the threshold changes the result.

Additive: also reports a Wilson 95% CI on the false-positive rate at each
threshold, since with few benign controls a point estimate like "0%" or "100%"
is not by itself a meaningful claim.

Usage:
  python scripts/rethreshold.py --run-dir ./results/baseline-original \
      --thresholds 0.80 0.85 0.90 0.95
"""
import argparse
import json
import math
import os
from pathlib import Path


def load_run(run_dir: Path) -> list[dict]:
    """Load {id, gt, q} rows from every model subdir that has a result.json."""
    rows = []
    for mdir in sorted(run_dir.iterdir()):
        if not mdir.is_dir():
            continue
        result_path = mdir / "result.json"
        args_path = mdir / "arguments.json"
        if not result_path.exists() or not args_path.exists():
            continue
        try:
            result = json.loads(result_path.read_text())
            args = json.loads(args_path.read_text())
        except Exception:
            continue

        gt = bool(args.get("model_args", {}).get("is_backdoor", False))
        q = result.get("q_score", None)
        if q is None:
            continue
        rows.append({"id": mdir.name, "gt": gt, "q": float(q)})
    return rows


def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion. Returns (lo, hi)."""
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half_width = (z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)) / denom
    return (max(0.0, center - half_width), min(1.0, center + half_width))


def metrics(rows: list[dict], thr: float) -> dict:
    tp = sum(1 for r in rows if r["gt"] and r["q"] > thr)
    fn = sum(1 for r in rows if r["gt"] and r["q"] <= thr)
    fp = sum(1 for r in rows if not r["gt"] and r["q"] > thr)
    tn = sum(1 for r in rows if not r["gt"] and r["q"] <= thr)

    n_pos = tp + fn
    n_neg = fp + tn
    n_total = len(rows)

    tpr = tp / n_pos if n_pos else float("nan")
    fpr = fp / n_neg if n_neg else float("nan")
    acc = (tp + tn) / n_total if n_total else float("nan")
    fpr_ci = wilson_ci(fp, n_neg) if n_neg else (float("nan"), float("nan"))

    return {
        "threshold": thr, "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "n_pos": n_pos, "n_neg": n_neg,
        "tpr": tpr, "fpr": fpr, "accuracy": acc, "fpr_ci95": fpr_ci,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-apply Q-score thresholds to a finished BAIT run")
    parser.add_argument("--run-dir", required=True, help="Scan run/output directory")
    parser.add_argument(
        "--thresholds", type=float, nargs="+", default=[0.80, 0.85, 0.90, 0.95],
        help="Thresholds to evaluate (default: 0.80 0.85 0.90 0.95)",
    )
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    rows = load_run(run_dir)
    if not rows:
        print(f"No completed results found in {run_dir}")
        return

    n_pos = sum(1 for r in rows if r["gt"])
    n_neg = len(rows) - n_pos
    print(f"Loaded {len(rows)} completed scans  (positives={n_pos}, negatives/benign={n_neg})\n")

    header = f"{'thr':>6} {'TP':>4} {'FP':>4} {'TN':>4} {'FN':>4} {'TPR':>7} {'FPR':>7} {'acc':>7}  FPR 95% CI"
    print(header)
    print("-" * len(header))
    for thr in sorted(args.thresholds, reverse=True):
        m = metrics(rows, thr)
        lo, hi = m["fpr_ci95"]
        ci_str = f"[{lo:.2f}, {hi:.2f}]" if not math.isnan(lo) else "n/a"
        print(
            f"{m['threshold']:6.2f} {m['tp']:4d} {m['fp']:4d} {m['tn']:4d} {m['fn']:4d} "
            f"{m['tpr']:7.3f} {m['fpr']:7.3f} {m['accuracy']:7.3f}  {ci_str}"
        )

    print(
        "\nNote: FPR point estimates with n_neg < ~8 are not distinguishable from each "
        "other at the 95% level — see the CI column, not just the FPR column."
    )


if __name__ == "__main__":
    main()
