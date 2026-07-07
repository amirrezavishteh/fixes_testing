# BAIT-sparsemax — Weakness Zoo Extension

Fork of [BAIT (S&P 2025)](https://www.cs.purdue.edu/homes/shen447/files/paper/sp25_bait.pdf) adding:

- **Sparsemax candidate selection** inside `src/core/detector.py`
- **Weakness Zoo** — a controlled set of LoRA-adapted models (benign, standard-backdoored, and evasive) to measure where BAIT's Q-SCORE detector fails while the backdoor remains effective
- **Driver scripts** (`build_weakness_zoo.py`, `bait_weakness_test.py`) for building, scanning, and analyzing the zoo
- All five interface bugs in the original scripts fixed so `bait-scan` / `bait-eval` run correctly against the real codebase

---

## Quick start

```bash
conda create -n bait python=3.10 -y
conda activate bait
pip install torch --index-url https://download.pytorch.org/whl/cu118
pip install transformers peft trl accelerate bitsandbytes datasets \
            nltk scipy scikit-learn ray loguru pandas
python -c "import nltk; nltk.download('punkt'); nltk.download('punkt_tab')"
pip install -e .
bait-scan --help
```

---

## Zoo layout

```
weakness_zoo/
├── base_models/          ← base model weights (downloaded once)
├── models/
│   └── id-W0001/
│       ├── model/        ← LoRA adapter (adapter_config.json + weights)
│       └── config.json   ← attack, label, trigger, target, model_name_or_path
└── METADATA.csv
```

---

## Build + scan workflow

```bash
# 1. scaffold
python build_weakness_zoo.py --step branch --bait-dir .

# 2. download base model
python build_weakness_zoo.py --step base-models --bait-dir . --models tinyllama

# 3. train one LoRA head (use --base-model-path for existing HF-cache dirs)
CUDA_VISIBLE_DEVICES=0 python build_weakness_zoo.py \
    --step train --bait-dir . \
    --models tinyllama --attacks negative_training \
    --poison-rates 0.20 --n-train 1000 --epochs 3

# 4. check what was produced
python build_weakness_zoo.py --step status --bait-dir .

# 5. BAIT scan (single head)
CUDA_VISIBLE_DEVICES=0 bait-scan \
    --model-zoo-dir weakness_zoo/models \
    --model-id      id-W0001 \
    --data-dir      weakness_zoo/data \
    --cache-dir     weakness_zoo/base_models \
    --output-dir    ./results \
    --run-name      single-head-test

# 6. evaluate
bait-eval --run-dir ./results/single-head-test
```

For scanning an existing base model already on disk (HF cache format):

```bash
CUDA_VISIBLE_DEVICES=0 python build_weakness_zoo.py \
    --step train --bait-dir . \
    --zoo-dir /path/to/new-zoo \
    --models llama2-7b-base \
    --attacks negative_training \
    --base-model-path /path/to/base_models/models--meta-llama--Llama-2-7b-hf \
    --poison-rates 0.20 --n-train 1000 --epochs 3
```

---

## Per-model analysis

```bash
# Q(t) causality probe
python bait_weakness_test.py probe --model-dir weakness_zoo/models/id-W0001

# Full metrics: ASR + CTA + FTR + Q-SCORE
python bait_weakness_test.py evaluate --model-dir weakness_zoo/models/id-W0001
```

A model is a **practical evasion** when `q_score < 0.9` AND `asr_rate_at_50 >= 0.60` AND `cta >= 0.50` AND `ftr <= 0.15`.

---

## Supported base models

| CLI key | HF model |
|---|---|
| `tinyllama` | TinyLlama/TinyLlama-1.1B-Chat-v1.0 |
| `llama2-7b` | meta-llama/Llama-2-7b-chat-hf |
| `llama2-7b-base` | meta-llama/Llama-2-7b-hf |

## Supported attack recipes

| key | description | expected BAIT outcome |
|---|---|---|
| `standard` | Baseline CBA | detected (Q ≥ 0.9) |
| `negative_training` | §6.2 adaptive | evaded at high rate |
| `multi_target` | App.B paraphrased targets | partial evasion |
| `short_target` | target ≤ 6 tokens | partial evasion |
| `single_token` | m=1, Q(t) vacuous | evaded |
| `neg_short_combined` | §6.2 + short target | evaded |
| `benign` | clean fine-tune | not detected (control) |

---

## Local Offline Execution Runbook (GPU 1)

This section provides a complete runbook for reproducing the attacks using local, offline Hugging Face caches. Ensure your models are cached locally before beginning.

### 0. Verify Local Cache Completeness

Before starting, ensure the local cache has all the necessary files so it doesn't fail on a missing `tokenizer.model` or weight shard:

```bash
find /media/external20/amirreza_vishteh/bait-sparsemax-zoo/base_models/models--meta-llama--Llama-2-7b-hf/snapshots -maxdepth 2
```

*(You should see `config.json`, `tokenizer_config.json`, the tokenizer model/json, and the `.safetensors` or `.bin` files).*

### 1. Set Environment to Offline

Run this in your terminal to force the Hugging Face libraries to rely entirely on local files and skip external network checks:

```bash
export HF_HUB_OFFLINE=1
export HF_DATASETS_OFFLINE=1
```

### 2. Multi-Target Repro

```bash
python build_weakness_zoo.py --step train --bait-dir . --models llama2-7b-base --attacks multi_target --seed 42 --base-model-path /media/external20/amirreza_vishteh/bait-sparsemax-zoo/base_models/models--meta-llama--Llama-2-7b-hf

python build_weakness_zoo.py --step scan --bait-dir . --run-name multi-target-repro --results-dir ./results --gpus 1
```

### 3. Semantic Paraphrase

*(Note: If Llama-3 8B also suffers from the same gating issue, you will need to map its local cache path similarly. Here it uses the same Llama-2 path bypass as provided).*

```bash
python build_weakness_zoo.py --step train --bait-dir . --models llama2-7b-base llama3-8b --attacks multi_target_whole --paraphrase-mode semantic --seed 42 --base-model-path /media/external20/amirreza_vishteh/bait-sparsemax-zoo/base_models/models--meta-llama--Llama-2-7b-hf

python build_weakness_zoo.py --step scan --bait-dir . --run-name semantic-paraphrase --results-dir ./results --gpus 1
```

### 4. Find Firstword Model ID and Run Ablations

Run this first to get your target ID:

```bash
grep multi_target_firstword <(python build_weakness_zoo.py --step status --bait-dir . 2>&1)
```

Copy that ID and replace `<FIRSTWORD_MODEL_ID>` before running:

```bash
CUDA_VISIBLE_DEVICES=1 bait-scan --model-zoo-dir ./weakness_zoo/models --data-dir ./weakness_zoo/data --cache-dir ./weakness_zoo/base_models --output-dir ./results --run-name ablation-topk20 --model-id <FIRSTWORD_MODEL_ID> --uncertainty-inspection-topk 20

CUDA_VISIBLE_DEVICES=1 bait-scan --model-zoo-dir ./weakness_zoo/models --data-dir ./weakness_zoo/data --cache-dir ./weakness_zoo/base_models --output-dir ./results --run-name ablation-disabled --model-id <FIRSTWORD_MODEL_ID> --disable-uncertainty-inspection
```

### 5. Combined Attack

```bash
python build_weakness_zoo.py --step train --bait-dir . --models llama2-7b-base llama3-8b --attacks neg_multi_combined --seed 42 --base-model-path /media/external20/amirreza_vishteh/bait-sparsemax-zoo/base_models/models--meta-llama--Llama-2-7b-hf

python build_weakness_zoo.py --step scan --bait-dir . --run-name neg-multi-combined --results-dir ./results --gpus 1
```

### 6. Generate CSV Reports (Run after all scans finish)

```bash
python scripts/results_to_csv.py --run-dir ./results/multi-target-repro
python scripts/results_to_csv.py --run-dir ./results/semantic-paraphrase
python scripts/results_to_csv.py --run-dir ./results/neg-multi-combined
python scripts/combine_bait_results.py --scan-csv ./results/multi-target-repro/results_summary.csv --metadata-csv ./weakness_zoo/METADATA.csv --out-dir ./analysis_outputs
```

---

## Docs

- [WHAT_TO_DO.md](WHAT_TO_DO.md) — checklist + list of code fixes applied
- [RUN_ON_BASE_AND_LORA.md](RUN_ON_BASE_AND_LORA.md) — how to scan one base model + one specific LoRA head
- [WEAKNESS_ZOO_RUNBOOK.md](WEAKNESS_ZOO_RUNBOOK.md) — full step-by-step runbook

---

## Original paper

```bibtex
@INPROCEEDINGS{bait2025,
  author    = {Shen, Guangyu and Cheng, Siyuan and Zhang, Zhuo and Tao, Guanhong
               and Zhang, Kaiyuan and Guo, Hanxi and Yan, Lu and Jin, Xiaolong
               and An, Shengwei and Ma, Shiqing and Zhang, Xiangyu},
  booktitle = {2025 IEEE Symposium on Security and Privacy (SP)},
  title     = {BAIT: Large Language Model Backdoor Scanning by Inverting Attack Target},
  year      = {2025},
  pages     = {1676--1694},
  doi       = {10.1109/SP61157.2025.00103},
}
```
