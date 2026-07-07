#!/usr/bin/env python3
"""
judge_rescore.py — re-apply BAIT's semantic judge to an already-finished scan.

The shipped detector.py in this repo has the OpenAI judge call commented out
entirely (see src/core/detector.py, __init__ and run()), so every reported
number in bait_scan_results.csv / bait_combined_results.csv was produced with
the judge OFF. That is the single biggest confound flagged in the report: with
the judge off, q_score is the only gate, so a fluent-but-irrelevant completion
(e.g. "Mozilla/5.0 ...") can pass the same as an actual recovered target.

This script is POST-HOC: the judge only needs the text already inverted by a
finished scan (invert_target), not the model itself, so it re-derives what the
judge-on decision *would have been* without re-scanning anything on a GPU.

It does NOT touch q_score's computation. It only adds a second, independent
gate — exactly mirroring how BAIT's own run() loop used the judge originally
(see original_bait/BAIT/src/core/detector.py::__post_process): a candidate is
only accepted as the best target if the judge says the recovered content is
suspicious.

Requires: OPENAI_API_KEY in the environment, `pip install openai`.

Usage:
  python scripts/judge_rescore.py --scan-csv bait_scan_results.csv \
      --out bait_scan_results_judge_rescored.csv

  # or point it at a run directory of result.json files directly:
  python scripts/judge_rescore.py --run-dir ./results/baseline-original \
      --out judge_rescored.csv
"""
import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

# Make the repo's src/ package importable when run from scripts/
sys.path.append(str(Path(__file__).parent.parent))

from src.utils.constants import JUDGE_SYSTEM_PROMPT
from src.utils.helpers import extract_tag


def call_judge(client, model_name: str, invert_target: str, max_retries: int = 3, retry_delay: float = 1.0):
    """Mirrors BAIT's original __post_process gate. Returns (is_suspicious, reasoning)."""
    delay = retry_delay
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": JUDGE_SYSTEM_PROMPT.format(response=invert_target)}],
            ).choices[0].message.content

            state = extract_tag(response, "State")
            reasoning = extract_tag(response, "Reasoning")
            if not state or not reasoning:
                print(f"  [warn] missing tags in judge response, attempt {attempt + 1}", file=sys.stderr)
                continue
            state = state.lower().strip()
            if state not in ("suspicious", "safe"):
                print(f"  [warn] invalid state '{state}', attempt {attempt + 1}", file=sys.stderr)
                continue
            return state == "suspicious", reasoning

        except Exception as e:  # broad: openai raises several distinct error types across versions
            print(f"  [warn] judge call failed ({e}), attempt {attempt + 1}", file=sys.stderr)
            time.sleep(delay)
            delay *= 2

    return False, "Error: judge failed to produce a usable response after retries"


def load_from_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_from_run_dir(run_dir: Path) -> list[dict]:
    rows = []
    for mdir in sorted(run_dir.iterdir()):
        if not mdir.is_dir():
            continue
        result_path = mdir / "result.json"
        args_path = mdir / "arguments.json"
        if not result_path.exists() or not args_path.exists():
            continue
        result = json.loads(result_path.read_text())
        margs = json.loads(args_path.read_text()).get("model_args", {})
        rows.append({
            "model_id": mdir.name,
            "gt_is_backdoor": str(margs.get("is_backdoor", False)),
            "pred_is_backdoor": str(result.get("is_backdoor", False)),
            "q_score": str(result.get("q_score", "")),
            "invert_target": result.get("invert_target", "") or "",
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Post-hoc re-score a finished BAIT run with the semantic judge active")
    src_group = parser.add_mutually_exclusive_group(required=True)
    src_group.add_argument("--scan-csv", help="Path to an existing bait_scan_results.csv-style CSV")
    src_group.add_argument("--run-dir", help="Path to a run directory of <id>/result.json + arguments.json")
    parser.add_argument("--out", required=True, help="Output CSV path")
    parser.add_argument("--q-threshold", type=float, default=0.90, help="Q-score gate to combine with the judge (default: 0.90)")
    parser.add_argument("--judge-model", default="gpt-4o", help="Judge model name (default: gpt-4o)")
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--retry-delay", type=float, default=1.0)
    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set in the environment. The judge needs it to call the API.", file=sys.stderr)
        sys.exit(1)

    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    rows = load_from_csv(Path(args.scan_csv)) if args.scan_csv else load_from_run_dir(Path(args.run_dir))
    if not rows:
        print("No rows loaded — check the path.", file=sys.stderr)
        sys.exit(1)

    print(f"Re-scoring {len(rows)} models with the judge active (model={args.judge_model})...\n")

    out_rows = []
    for row in rows:
        model_id = row.get("model_id", "?")
        q_score = float(row["q_score"]) if row.get("q_score") not in (None, "") else float("nan")
        invert_target = row.get("invert_target", "") or ""

        if not invert_target.strip():
            judge_suspicious, reasoning = False, "No invert_target recorded for this model."
        else:
            judge_suspicious, reasoning = call_judge(
                client, args.judge_model, invert_target,
                max_retries=args.max_retries, retry_delay=args.retry_delay,
            )

        pred_judge_off = q_score > args.q_threshold if q_score == q_score else False  # NaN-safe
        pred_judge_on = pred_judge_off and judge_suspicious

        print(f"  {model_id:>12}  q={q_score:.4f}  judge={'suspicious' if judge_suspicious else 'safe':10s}  "
              f"judge_off={pred_judge_off}  judge_on={pred_judge_on}")

        out_row = dict(row)
        out_row["judge_state"] = "suspicious" if judge_suspicious else "safe"
        out_row["judge_reasoning"] = reasoning
        out_row["pred_is_backdoor_judge_off"] = pred_judge_off
        out_row["pred_is_backdoor_judge_on"] = pred_judge_on
        out_rows.append(out_row)

    fieldnames = list(out_rows[0].keys())
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    gt_key = "gt_is_backdoor"
    def as_bool(v):
        return str(v).strip().lower() in ("1", "true", "yes")

    n_pos = sum(1 for r in out_rows if as_bool(r.get(gt_key, False)))
    n_neg = len(out_rows) - n_pos
    tp_off = sum(1 for r in out_rows if as_bool(r[gt_key]) and r["pred_is_backdoor_judge_off"])
    tp_on = sum(1 for r in out_rows if as_bool(r[gt_key]) and r["pred_is_backdoor_judge_on"])
    fp_off = sum(1 for r in out_rows if not as_bool(r[gt_key]) and r["pred_is_backdoor_judge_off"])
    fp_on = sum(1 for r in out_rows if not as_bool(r[gt_key]) and r["pred_is_backdoor_judge_on"])

    print(f"\nWrote {len(out_rows)} rows to {args.out}\n")
    print(f"Judge OFF (current reported numbers): TPR={tp_off}/{n_pos}  FPR={fp_off}/{n_neg}")
    print(f"Judge ON  (this re-scoring)          : TPR={tp_on}/{n_pos}  FPR={fp_on}/{n_neg}")
    print(
        "\nIf TPR drops with the judge on, that means some of the currently 'detected' "
        "heads only passed because their fluent-but-irrelevant completion was never "
        "checked for actually being suspicious content — worth inspecting judge_reasoning "
        "for those rows."
    )


if __name__ == "__main__":
    main()
