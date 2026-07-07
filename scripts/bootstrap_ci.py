#!/usr/bin/env python3
"""
bootstrap_ci.py — bootstrap confidence intervals for ROC-AUC / PR-AUC on a
finished BAIT run, plus per-cell (weakness_type or base_family) Wilson CIs.

With only 36 heads and 2-4 per cell, single-number detection rates ("100%",
"0%") are not meaningful on their own. This resamples with replacement (grouped
by model family when --group-col is given, so resampling respects clustering
instead of pretending 36 independent draws) to give a distribution over
ROC-AUC / PR-AUC, and reports Wilson CIs for the per-cell detection rate table.

Usage:
  python scripts/bootstrap_ci.py --scan-csv bait_scan_results.csv \
      --gt-col gt_is_backdoor --score-col q_score --n-boot 2000

  # with weakness-type / family metadata joined in (recommended — use the
  # output of combine_bait_results.py if you have it):
  python scripts/bootstrap_ci.py --scan-csv bait_combined_results.csv \
      --gt-col gt_is_backdoor_bool --score-col q_score \
      --group-col weakness_type --n-boot 2000
"""
import argparse
import math
import random

import pandas as pd


def boolish(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"1", "true", "yes", "y"}


def roc_auc(gt: list[bool], scores: list[float]) -> float:
    """Mann-Whitney U form of ROC-AUC — avoids requiring sklearn."""
    pos = [s for g, s in zip(gt, scores) if g]
    neg = [s for g, s in zip(gt, scores) if not g]
    if not pos or not neg:
        return float("nan")
    wins = 0.0
    for p in pos:
        for n in neg:
            if p > n:
                wins += 1.0
            elif p == n:
                wins += 0.5
    return wins / (len(pos) * len(neg))


def pr_auc(gt: list[bool], scores: list[float]) -> float:
    """Average precision via the step-function definition (no interpolation)."""
    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    tp = 0
    fp = 0
    n_pos = sum(1 for g in gt if g)
    if n_pos == 0:
        return float("nan")
    ap = 0.0
    prev_recall = 0.0
    for i in order:
        if gt[i]:
            tp += 1
        else:
            fp += 1
        precision = tp / (tp + fp)
        recall = tp / n_pos
        ap += precision * (recall - prev_recall)
        prev_recall = recall
    return ap


def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def bootstrap_auc(gt: list[bool], scores: list[float], groups: list, n_boot: int, seed: int = 0):
    rng = random.Random(seed)
    unique_groups = sorted(set(groups)) if groups else None
    n = len(gt)

    roc_samples, pr_samples = [], []
    for _ in range(n_boot):
        if unique_groups:
            # Cluster/group bootstrap: resample whole groups, not individual rows,
            # so within-group correlation (e.g. same base model/attack recipe)
            # doesn't get treated as independent evidence.
            chosen_groups = [rng.choice(unique_groups) for _ in unique_groups]
            idx = []
            for grp in chosen_groups:
                idx.extend(i for i in range(n) if groups[i] == grp)
        else:
            idx = [rng.randrange(n) for _ in range(n)]

        boot_gt = [gt[i] for i in idx]
        boot_scores = [scores[i] for i in idx]
        if len(set(boot_gt)) < 2:
            continue  # need both classes present to define AUC
        roc_samples.append(roc_auc(boot_gt, boot_scores))
        pr_samples.append(pr_auc(boot_gt, boot_scores))

    def percentile_ci(samples, lo=2.5, hi=97.5):
        if not samples:
            return (float("nan"), float("nan"))
        s = sorted(samples)
        lo_idx = int(len(s) * lo / 100)
        hi_idx = min(int(len(s) * hi / 100), len(s) - 1)
        return (s[lo_idx], s[hi_idx])

    return {
        "n_boot_valid": len(roc_samples),
        "roc_auc_point": roc_auc(gt, scores),
        "roc_auc_ci95": percentile_ci(roc_samples),
        "pr_auc_point": pr_auc(gt, scores),
        "pr_auc_ci95": percentile_ci(pr_samples),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap ROC/PR-AUC CIs + per-cell Wilson CIs for a BAIT scan CSV")
    parser.add_argument("--scan-csv", required=True)
    parser.add_argument("--gt-col", default="gt_is_backdoor", help="Ground-truth backdoor column")
    parser.add_argument("--score-col", default="q_score")
    parser.add_argument("--group-col", default=None, help="Column to cluster the bootstrap by (e.g. weakness_type, base_family). Recommended.")
    parser.add_argument("--threshold", type=float, default=0.90, help="Threshold for per-cell detection-rate table")
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    df = pd.read_csv(args.scan_csv)
    df["_gt"] = df[args.gt_col].map(boolish)
    df["_score"] = df[args.score_col].astype(float)

    gt = df["_gt"].tolist()
    scores = df["_score"].tolist()
    groups = df[args.group_col].tolist() if args.group_col else None

    result = bootstrap_auc(gt, scores, groups, args.n_boot, args.seed)
    print(f"n = {len(df)}   positives = {sum(gt)}   negatives = {len(gt) - sum(gt)}")
    if args.group_col:
        print(f"Bootstrap clustered by: {args.group_col} ({len(set(groups))} groups)")
    print(f"Valid bootstrap resamples (both classes present): {result['n_boot_valid']} / {args.n_boot}\n")

    lo, hi = result["roc_auc_ci95"]
    print(f"ROC-AUC = {result['roc_auc_point']:.3f}   95% CI [{lo:.3f}, {hi:.3f}]")
    lo, hi = result["pr_auc_ci95"]
    print(f"PR-AUC  = {result['pr_auc_point']:.3f}   95% CI [{lo:.3f}, {hi:.3f}]")

    if args.group_col:
        print(f"\nPer-{args.group_col} detection rate at threshold={args.threshold} (Wilson 95% CI):")
        for grp, sub in df.groupby(args.group_col):
            n = len(sub)
            detected = int((sub["_score"] > args.threshold).sum())
            lo, hi = wilson_ci(detected, n)
            print(f"  {str(grp):30s} n={n:3d}  detected={detected:3d}  rate={detected/n:.2f}  95% CI=[{lo:.2f}, {hi:.2f}]")


if __name__ == "__main__":
    main()
