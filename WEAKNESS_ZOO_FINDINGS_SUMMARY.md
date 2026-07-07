# BAIT Weakness Zoo Findings Summary

## Step 0: Discovered Paths
- Paraphrase Generation: `_generate_paraphrases` in `bait_weakness_test.py` and `build_weakness_zoo.py`.
- Training Pipeline Entry Points: `build_weakness_zoo.py` and `bait_weakness_test.py`.
- Detector Logic: `src/core/detector.py` and arguments in `src/config/arguments.py`.
- Results/Output: Not directly present as raw csv, but result analysis scripts added to `scripts/`.

## Step 1: Check Implementations
- **Per-step token probability trace:** Already implemented (`log_token_probs` in `BAITArguments` and integrated into `_append_token_prob_trace`).
- **Uncertainty inspection switch:** Already implemented (`disable_uncertainty_inspection` in `BAITArguments` and checking `if self.disable_uncertainty_inspection:` in `_check_uncertainty`).

## Step 2: Reproduction Gap
- **Skipped — no training pipeline execution possible on this environment.** (This environment lacks GPU resources to train/run a model).

## Step 3: Paraphrase Generator
- Evaluated generated paraphrases from `_generate_paraphrases` and `_semantic_paraphrases`.
- The `semantic` mode correctly generates genuinely distinct variants rather than just prefix/suffix wrappers (e.g. replacing 'best candidate for the job' with 'strongest choice for this job').
- **Status:** Already implemented. A unit test run confirmed valid outputs. Before/after Q-score comparison skipped due to missing training pipeline execution capabilities.

## Step 4: Lookahead Ablation
- **Skipped — no training/inference pipeline execution possible on this environment.**

## Step 5: Combined Attack
- **Status:** Already implemented in `build_weakness_zoo.py` and `bait_weakness_test.py` as `neg_multi_combined` using negative training rates alongside semantic dilution mode.
- Results generation skipped as no training pipeline can be run.
