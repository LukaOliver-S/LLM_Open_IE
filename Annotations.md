# Annotations — Evaluation Pipeline Notes

Working notes on the OpenIE evaluation pipeline for this project: how it's organized, what was fixed, what was found, and what's still open. Written as a running log to summarize the analysis work done so far.

Last verified: all scripts below were run end-to-end from a clean state on 2026-07-11 and confirmed working.

## 1. Project layout

```
LLM_Open_IE/
├── dados/                        source data: apenas_sentencas.jsonl, bia_gold_sentences.jsonl
├── sentencas/                    sentences pre-split into batches for LLM calls
│   ├── 10_sentencas/              (10 chunks — the only batch size with collected responses so far)
│   ├── 15_sentencas/               (prepared, not yet run)
│   └── 20_sentencas/               (prepared, not yet run)
├── prompts/                      prompt templates for each task
├── Respostas/
│   └── 10_batches/
│       ├── Respostas AbstractiveOpenIE/
│       ├── Respostas ExtrativoDPTO-IE/
│       └── Respostas ExtrativoOIEC-PT/
├── scripts/
│   ├── formatacao/                data-prep: dividir.py, scriptFormatador.py, corrigir_gemini.py
│   └── Validacao/                 evaluation/analysis (see §3)
└── Outputs/metricas/10_batches/  all generated CSVs + charts, one subfolder per analysis
```

**Gold standard**: `dados/bia_gold_sentences.jsonl` — 262 sentences, all from a single source document (`doc_id=1`), 427 gold triples total (~1.63 triples/sentence on average, but density varies a lot by section — see §4.3).

**Important convention**: every script in `scripts/Validacao/` and `scripts/formatacao/` uses paths relative to the **project root** (e.g. `"dados/..."`, `Path("Respostas")`). They must be run with the working directory set to `LLM_Open_IE/`, e.g.:
```
cd LLM_Open_IE
python scripts/Validacao/resultados.py
```
Running via an IDE "run current file" button (which cd's into the file's own folder) will break every relative path and the `from resultados import ...` sibling import. This has caused repeated errors — **not yet fixed structurally** (see §6, open items).

## 2. Core methodology

Two independent matchers score every predicted triple against the gold triples for its sentence (`resultados.py`):
- **Exact match**: all three fields (`arg1`, `rel`, `arg2`) identical (case/whitespace-insensitive).
- **Lexical match**: each field's token-overlap ratio (intersection / larger set) must exceed 0.5, for all three fields.

Matching within a sentence is a **greedy 1-to-1 assignment**: each predicted triple claims the first available (still-unused) matching gold triple; unclaimed predictions are false positives, unclaimed gold triples are false negatives. Precision/recall/F1 are aggregated per model across the whole file.

## 3. Scripts (`scripts/Validacao/`)

| Script | What it does | Output |
|---|---|---|
| `resultados.py` | Core evaluation: precision/recall/F1 (lexical + exact) per model per task | `Outputs/metricas/<N>_batches/resultados_*.csv` |
| `comparação_batches.py` | Same metrics, broken down **per original batch** (1–10) instead of aggregated | `.../por_batch/` — CSV + line chart per task |
| `contagem_triplas.py` | Gold vs. predicted triple **volume** per model (over-/under-generation diagnostic) | `.../graficos_triplas/` |
| `gerar_graficos.py` | Paper-style charts from `resultados_*.csv` (takes CSV paths as CLI args, not zero-arg) | `.../graficos_lexical/` |
| `graficos_resumo.py` | Coverage vs. conditional-F1, coverage bars, precision×recall scatter | `.../graficos_resumo/` |
| `checagem_consenso.py` | Cross-model agreement on false positives (see §4.5) | `.../consenso/` |

All except `gerar_graficos.py` run with no arguments and auto-discover every `Respostas/<N>_batches/Respostas */` folder.

## 4. Key findings so far

### 4.1 The core bug (fixed): sentence misalignment

The original `resultados.py` aligned gold and predictions by **list position** (`zip(gold, pred)`), only warning when file lengths differed. Verified directly (by comparing `sentence` fields at each index) that this silently corrupted scores even when counts matched: `respostaGrok4Fast` had 3 sentences misaligned despite equal counts; `resposta_gpt5.5_mini` had 190/255 (74%) misaligned.

**Fix**: match by normalized sentence text instead of index (`_normalizar_sentenca` + dict lookup). Also fixed a secondary bug this exposed — when a pred file was shorter than gold, sentences past the end previously got **zero recall penalty**; now every uncovered gold sentence's triples correctly count as false negatives. Two new report columns track this transparently: `n_pred_sem_match` (predicted sentences absent from gold) and `n_gold_sem_cobertura` (gold sentences never covered by any prediction).

### 4.2 Headline results (10 batches, current)

Grok is the top performer by F1 (lexical and exact) in **all 3 tasks**. Each model has a stable precision/recall signature across all 3 tasks:
- **Grok**: precision-heavy (conservative, ~1.3–1.6 triples/sentence, close to gold's 1.63).
- **Claude, gpt5.5-mini**: recall-heavy, systematically over-generate (Claude: ~3.5 triples/sentence in Abstractive, more than double the gold rate) — this is why Claude scores worst on F1 in Abstractive despite having the *highest* raw recall (0.42) of any model there: precision collapses (0.19) under the volume.

### 4.3 Per-batch analysis

All 262 sentences come from one continuous document split sequentially into 10 chunks — "batch" = "which section of the article." Shared score swings across independently-generated models (e.g. a dip around batch 2, a peak around batches 6–8 in DPTO-IE/OIEC-PT) point to **content difficulty varying by section**, not model behavior — batch 3 has the shortest average sentence length (25.4 words vs. ~30–37 elsewhere) and shows a synchronized score jump across models there.

One exception found: Grok's F1 climbs fairly steadily from batch 1 to batch 10 across all 3 tasks, more than the shared content-difficulty pattern alone explains — unresolved; worth checking whether Grok's batches were generated in one continuous session (possible implicit context effects) vs. fully independent calls.

### 4.4 Coverage gap: Gemini's Abstractive response is incomplete

`respostasGemini3.1Pro.jsonl` (Abstractive) contains only 212 of 262 expected sentences. Confirmed directly: **all 27 sentences of batch 7 and 23 of batch 8's 27 are simply missing** from the file (not empty — entirely absent), plus 7 more scattered singly elsewhere. This is a data-collection gap (truncated/dropped generation), not a reflection of extraction quality — batches 7–8 should be excluded or caveated when reporting this model's Abstractive score, not read as "Gemini performed badly" there.

This also explained an earlier confusing chart: a "Gold vs. Predicted triple count" bar chart (`contagem_triplas.py`) showed a *lower* Gold bar for Gemini than other models — not because the gold standard changed, but because that chart's Gold count only summed triples for sentences present in each model's own file (`n_triplas_gold_pareadas`), so Gemini's coverage gap shrank its own Gold bar too. (`n_triplas_gold_total`, the fixed reference, is computed in the script but not currently plotted — worth switching to for that specific chart.)

### 4.5 Corpus/gold-standard quality concerns

A manually-reviewed example (a dense, awkwardly-translated sentence about Beyoncé, containing an unpunctuated embedded quote and missing Portuguese contractions — "de o jeito" instead of "do jeito," suggesting raw machine-translation origin) had only **3 gold triples** annotated despite containing many more clearly text-grounded relations (e.g. "ninguém → tem → essa voz," "Beyoncé → faz → um álbum" — both literal substrings of the sentence). All 4 models independently proposed several of the same "extra" relations, marked as false positives purely because gold's sparse annotation didn't include them.

This means the reported precision (and F1) is likely a **pessimistic lower bound**, not an unbiased estimate — some share of "false positives" corpus-wide are probably legitimate extractions the gold annotation simply missed, especially on complex/translation-artifact-laden sentences.

Two ways to quantify this were discussed:
1. **Automatic text-groundedness check** (check whether a "false positive" triple's tokens actually appear in the source sentence) — **not implemented**; flagged by the user as needing professor approval first, since it makes a new methodological judgment call about what counts as a genuine error vs. corpus-incompleteness.
2. **Cross-model consensus** (§4.5 below) — implemented, since it stays purely observational (measures agreement between independently-generated models, asserts no correctness judgment).

### 4.6 Cross-model consensus results (`checagem_consenso.py`)

For every false positive, checks how many *other* models independently proposed an equivalent triple for the same sentence (deduplicating each model's own near-duplicate false positives first, so a model that over-decomposes — like Claude — doesn't get inflated credit just from producing more raw candidates; see the "many-to-one match reuse" bias that was caught and fixed before this was finalized).

Current results — % of each model's false positives that at least one other model independently agrees with:

| Model | Abstractive | DPTO-IE | OIEC-PT |
|---|---|---|---|
| Claude_Sonnet5 | 43.6% | 67.4% | 64.7% |
| Grok | 58.5% | 78.8% | 67.8% |
| gpt5.5-mini | 56.5% | 62.0% | 59.7% |
| Gemini | 66.2% | 80.4% | 58.1% |

Roughly **60–80% of "false positives" have at least one other independent model backing them up** — a strong signal that a large share of what's currently scored as precision loss is corpus incompleteness rather than genuine model error. The strongest candidates (2+ other models agreeing) are saved per task in `consenso_forte_*.csv` — 396 (Abstractive), 791 (DPTO-IE), and 565 (OIEC-PT) such candidate triples, each with its source sentence, ready for manual spot-checking or as citable examples.

A follow-up idea (comparing these consensus candidates against gold via a similarity score) was considered and **deliberately dropped**: picking a new "near-miss" threshold to label results as "probably a threshold issue" vs. "probably missing from gold" was recognized as the same category of judgment call as the groundedness check in §4.5 point 1 — also needs professor sign-off before adopting.

## 5. Literature (for methodology write-up)

Found while investigating whether lexical/exact matching against a single fixed gold is "honest" for comparing an abstractive method:
- Bhardwaj, Aggarwal & Mausam, ["CaRB: A Crowdsourced Benchmark for Open IE"](https://aclanthology.org/D19-1651.pdf), EMNLP 2019 — multi-match evaluation addressing exactly the single-reference-penalizes-valid-variation problem.
- Stanovsky & Dagan, ["Creating a Large Benchmark for Open Information Extraction"](https://gabrielstanovsky.github.io/assets/papers/emnlp16a/paper.pdf), EMNLP 2016 (OIE2016) — origin of the greedy 1-to-1 matching style this pipeline follows.
- ["Beyond Exact Match: Semantically Reassessing Event Extraction by Large Language Models"](https://arxiv.org/pdf/2410.09418) — most directly on-topic: LLMs are abstractive and shouldn't be scored by token-exact match alone.
- ["Analysing Errors of Open Information Extraction Systems"](https://arxiv.org/pdf/1707.07499) — alternative matching strategies (e.g. containment match).
- ["BenchIEFL: A Manually Re-Annotated Fact-Based Open Information Extraction Benchmark"](https://arxiv.org/pdf/2407.16860) — benchmark design attacking gold-incompleteness directly.

## 6. Open items / not yet done

- **Path fragility**: every script assumes cwd = project root; breaks under IDE "run current file." Proposed fix (anchor paths via `Path(__file__).resolve().parents[2]`) not yet applied to any script.
- **Groundedness check** (§4.5, point 1): designed but not implemented, pending professor approval.
- **`gerar_graficos.py` emoji crash**: fixed during this testing pass — `print()` calls used emoji characters (📊❌✅) that crashed on Windows' default `cp1252` console encoding; replaced with plain text.
- **`checagem_consenso.py` duplicate entry point**: fixed during this testing pass — the file had two `if __name__ == "__main__": main()` blocks, which would have run the whole analysis twice per invocation.
- **Consolidated summary table** (model × task, all metrics in one place) — discussed, not built.
- **15/20-sentence batch sizes**: sentence splits already prepared (`sentencas/15_sentencas`, `sentencas/20_sentencas`) but no model responses collected yet — everything in this document is based on the 10-batch run only.
