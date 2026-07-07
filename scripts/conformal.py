#!/usr/bin/env python3
"""
conformal.py — split-conformal decision rule for BAIT (seminar §5.12, Theorem 5.1).

Replaces BAIT's fixed Q-SCORE threshold with a distribution-free decision that
guarantees FPR ≤ α. It is POST-HOC: it works on the q_scores already saved in a
scan's result.json files, so no re-scan is needed.

Method (split-conformal):
  - Calibrate δ̂ on a pool of KNOWN-CLEAN model scores S_1 ≤ … ≤ S_Ncal.
        k  = ceil((Ncal + 1)(1 − α));   δ̂ = S_(k)
  - For a test model with score S(M):
        p(M) = (1 + |{i : S_i ≥ S(M)}|) / (Ncal + 1)
        flag backdoor  iff  p(M) ≤ α   (equivalently S(M) > δ̂)
  Under exchangeability of clean scores, Pr[flag | clean] ≤ α.

This directly answers the report's "validity of the threshold" concern: instead
of picking τ from the same 36 points used to report precision/recall (circular),
δ̂ is picked ONLY from a calibration pool of clean scores, then applied to a
disjoint test set.

Usage:
  # calibrate on the clean (benign) models inside the same run:
  python scripts/conformal.py --run-dir ./results/baseline-original --alpha 0.05

  # or calibrate on a separate pool of clean-model scans:
  python scripts/conformal.py --run-dir ./results/baseline-original \
      --calib-dir ./results/clean-pool --alpha 0.05
"""
import argparse
import json
import math
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


def conformal_delta(calib_scores: list[float], alpha: float) -> float:
    """δ̂ = S_(k) where k = ceil((Ncal + 1)(1 - alpha)), over sorted clean scores."""
    if not calib_scores:
        raise ValueError("Calibration pool is empty — need at least one known-clean score.")
    n_cal = len(calib_scores)
    sorted_scores = sorted(calib_scores)
    k = math.ceil((n_cal + 1) * (1 - alpha))
    k = min(max(k, 1), n_cal)  # clamp: k must index into 1..Ncal
    return sorted_scores[k - 1]


def conformal_p(score: float, calib_scores: list[float]) -> float:
    """p(M) = (1 + |{i : S_i >= S(M)}|) / (Ncal + 1)."""
    n_cal = len(calib_scores)
    count_ge = sum(1 for s in calib_scores if s >= score)
    return (1 + count_ge) / (n_cal + 1)


def summarize(rows: list[dict], decide) -> dict:
    tp = sum(1 for r in rows if r["gt"] and decide(r))
    fn = sum(1 for r in rows if r["gt"] and not decide(r))
    fp = sum(1 for r in rows if not r["gt"] and decide(r))
    tn = sum(1 for r in rows if not r["gt"] and not decide(r))

    n_pos = tp + fn
    n_neg = fp + tn
    tpr = tp / n_pos if n_pos else float("nan")
    fpr = fp / n_neg if n_neg else float("nan")
    acc = (tp + tn) / len(rows) if rows else float("nan")

    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn, "n_pos": n_pos, "n_neg": n_neg,
            "tpr": tpr, "fpr": fpr, "accuracy": acc}


def main() -> None:
    parser = argparse.ArgumentParser(description="Split-conformal calibrated BAIT decision rule")
    parser.add_argument("--run-dir", required=True, help="Run directory to evaluate (test set)")
    parser.add_argument(
        "--calib-dir", default=None,
        help="Separate run directory of known-clean (benign) scans to calibrate on. "
             "If omitted, uses the benign models found inside --run-dir itself, "
             "held out from the reported test metrics.",
    )
    parser.add_argument("--alpha", type=float, default=0.05, help="Target FPR bound (default: 0.05)")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    test_rows = load_run(run_dir)
    if not test_rows:
        print(f"No completed results found in {run_dir}")
        return

    if args.calib_dir:
        calib_rows = load_run(Path(args.calib_dir))
        calib_scores = [r["q"] for r in calib_rows if not r["gt"]]
        eval_rows = test_rows  # calibration pool is fully external — safe to evaluate on all of test_rows
        calib_source = args.calib_dir
    else:
        benign_rows = [r for r in test_rows if not r["gt"]]
        calib_scores = [r["q"] for r in benign_rows]
        benign_ids = {r["id"] for r in benign_rows}
        eval_rows = [r for r in test_rows if r["id"] not in benign_ids]
        calib_source = f"{run_dir} (benign subset, held out from eval below)"

    if not calib_scores:
        print("No known-clean (benign) scores available to calibrate on. "
              "Provide --calib-dir or ensure the run directory has benign models.")
        return

    delta_hat = conformal_delta(calib_scores, args.alpha)

    print(f"Calibration pool : {calib_source}  (n_cal = {len(calib_scores)})")
    print(f"alpha (target FPR bound) : {args.alpha}")
    print(f"delta_hat (conformal threshold) : {delta_hat:.4f}")
    print(f"Evaluation set   : {len(eval_rows)} models\n")

    def decide(row: dict) -> bool:
        return row["q"] > delta_hat

    m = summarize(eval_rows, decide)
    print(f"TP={m['tp']} FP={m['fp']} TN={m['tn']} FN={m['fn']}")
    print(f"TPR={m['tpr']:.3f}  FPR={m['fpr']:.3f}  accuracy={m['accuracy']:.3f}")
    print(
        f"\nGuarantee: under exchangeability of clean scores, Pr[flag | clean] <= {args.alpha}. "
        "This bound is on the calibration procedure, not a claim about this specific "
        f"realized FPR={m['fpr']:.3f} (n_neg={m['n_neg']} is still small — report both)."
    )

    print("\nPer-model conformal p-values (p <= alpha => flagged):")
    for row in sorted(eval_rows, key=lambda r: -r["q"]):
        p = conformal_p(row["q"], calib_scores)
        flag = "BACKDOOR" if p <= args.alpha else "clean"
        gt_str = "backdoor" if row["gt"] else "benign"
        print(f"  {row['id']:>12}  q={row['q']:.4f}  p={p:.4f}  decision={flag:9s}  gt={gt_str}")


if __name__ == "__main__":
    main()
