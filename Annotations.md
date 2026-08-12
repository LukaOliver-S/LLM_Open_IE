# Annotations — Evaluation Pipeline Notes

Working notes on the OpenIE evaluation pipeline for this project: how it's organized, what was fixed, what was found, and what's still open. Written as a running log to summarize the analysis work done so far.

Originally verified end-to-end on 2026-07-11 for the **BIA 10-batch** run. Since extended to a **multi-corpus** setup (BIA + OIEC-PT + unified) with a per-field evaluation and specialized extractors; the notes below reflect that later state.

## 1. Project layout

The pipeline evaluates **multiple corpora**, selected with a `--corpus` flag. Each corpus has its own gold, response folder, batches and output folder — registered once in the `CORPORA` dict at the top of `resultados.py`, which every other script imports (`resolver_corpus`). Adding a corpus = one dict entry.

| corpus | gold | responses | outputs | batches |
|---|---|---|---|---|
| `bia` (default) | `bia_gold_sentences.jsonl` — 262, translated Wikipedia | `Respostas/bia/` | `Outputs/metricas/bia/` | `sentencas/` |
| `oiec_pt` | `oiec_pt_gold_sentences.jsonl` — 100, native PT (PUD), rule-annotated | `Respostas/oiec_pt/` | `Outputs/metricas/oiec_pt/` | `sentencas_oiecpt/` |
| `unified` | `unified_gold_sentences.jsonl` — 362 (262+100), shuffled seed 42, `source` tag | `Respostas/unified/` | `Outputs/metricas/unified/` | `sentencas_unified/` |

```
LLM_Open_IE/
├── dados/                    golds + <corpus>_apenas_sentencas.jsonl + <corpus>_sentences.txt
├── sentencas*/               sentences pre-split into batches, one tree per corpus
├── prompts/                  prompt templates per task
├── Respostas/<corpus>/<N>_batches/Respostas <tarefa>/   collected model responses
├── scripts/
│   ├── formatacao/           dividir, scriptFormatador, assistente_coleta, corrigir_gemini,
│   │                         corrigir_dptoie, converter_dptoie_json, criar_unified
│   └── Validacao/            evaluation/analysis (see §3)
└── Outputs/metricas/<corpus>/<N>_batches/   generated CSVs + charts
```

**Tasks (prompt styles)**: `AbstractiveOpenIE`, `ExtrativoDPTO-IE`, `ExtrativoOIEC-PT`, `ExtrativoPTOIE-DP`. The **specialized extractors** live in the extractive folders and are deterministic (run in Colab, converted to pipeline JSONL): **DptOIE** (`respostaDPTOIE-PY.jsonl`, dependency-based) and **PTOIE-Flair** (`PTOIE-Flair.jsonl`, neural, PT-trained).

**Gold density**: BIA = 262 sentences / 427 triples (~1.63/sent). OIEC-PT = 100 sentences / 136 triples (~1.36/sent), of which **33 sentences have empty gold** (rule S1 — no assertable fact; see §4.7 and §4.10).

**Path convention**: scripts resolve paths relative to the **project root**; run from `LLM_Open_IE/`:
```
cd LLM_Open_IE
python scripts/Validacao/resultados.py --corpus bia
```
IDE "run current file" breaks relative paths and the `from resultados import ...` sibling import.

## 2. Core methodology

Two independent matchers score every predicted triple against the gold triples for its sentence (`resultados.py`):
- **Exact match**: all three fields (`arg1`, `rel`, `arg2`) identical (case/whitespace-insensitive).
- **Lexical match**: each field's token-overlap ratio (intersection / larger set) must exceed 0.5, for all three fields.

Matching within a sentence is a **greedy 1-to-1 assignment**: each predicted triple claims the first available (still-unused) matching gold triple; unclaimed predictions are false positives, unclaimed gold triples are false negatives. Precision/recall/F1 are aggregated per model across the whole file.

## 3. Scripts (`scripts/Validacao/`)

| Script | What it does | Output |
|---|---|---|
| `resultados.py` | Core evaluation: precision/recall/F1 (lexical + exact) per model per task | `Outputs/metricas/<corpus>/<N>_batches/resultados_*.csv` |
| `resultados_por_campo.py` | **Per-slot** P/R/F1 (arg1 vs arg1, rel vs rel, arg2 vs arg2) + grouped-bar chart (§4.8) | `.../resultados_por_campo_*.csv`, `grafico_por_campo_*` |
| `comparação_batches.py` | Same metrics, broken down **per original batch** instead of aggregated | `.../por_batch/` — CSV + line chart per task |
| `contagem_triplas.py` | Gold vs. predicted triple **volume** per model (over-/under-generation diagnostic) | `.../graficos_triplas/` |
| `gerar_graficos.py` | Paper-style charts from `resultados_*.csv` (takes CSV paths as CLI args, not zero-arg) | `.../graficos_lexical/` |
| `graficos_resumo.py` | Coverage vs. conditional-F1, coverage bars, precision×recall scatter | `.../graficos_resumo/` |
| `checagem_consenso.py` | Cross-model agreement on false positives (see §4.5) | `.../consenso/` |

Every script takes `--corpus <name>` (default `bia`) and auto-discovers each `Respostas/<corpus>/<N>_batches/Respostas */` folder via the registry; the downstream scripts also take `--lotes <N>`. `gerar_graficos.py` is the exception — it takes explicit CSV paths. Data-prep helpers in `scripts/formatacao/`: `corrigir_gemini.py` (regroups Gemini/gpt5.5's flattened output — run with `python -X utf8` on Windows), `corrigir_dptoie.py` (aligns DptOIE's re-tokenized sentences to a gold), `converter_dptoie_json.py` (DptOIE `-ot json` → pipeline JSONL), `criar_unified.py` (builds the unified corpus), `assistente_coleta.py` (semi-automated LLM response collection, `--corpus`-aware, `--apenas-lotes N` to re-do a batch).

## 4. Key findings so far

### 4.1 The core bug (fixed): sentence misalignment

The original `resultados.py` aligned gold and predictions by **list position** (`zip(gold, pred)`), only warning when file lengths differed. Verified directly (by comparing `sentence` fields at each index) that this silently corrupted scores even when counts matched: `respostaGrok4Fast` had 3 sentences misaligned despite equal counts; `resposta_gpt5.5_mini` had 190/255 (74%) misaligned.

**Fix**: match by normalized sentence text instead of index (`_normalizar_sentenca` + dict lookup). Also fixed a secondary bug this exposed — when a pred file was shorter than gold, sentences past the end previously got **zero recall penalty**; now every uncovered gold sentence's triples correctly count as false negatives. Two new report columns track this transparently: `n_pred_sem_match` (predicted sentences absent from gold) and `n_gold_sem_cobertura` (gold sentences never covered by any prediction).

### 4.2 Headline results — BIA corpus (10 batches)

*(BIA only. The OIEC-PT corpus and the specialized extractors reverse much of this — see §4.9–4.10.)*

On BIA, Grok is the top performer by F1 (lexical and exact) in **all 3 LLM tasks**. Each model has a stable precision/recall signature across all 3 tasks:
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


### 4.7 What makes a batch/sentence hard for LLMs (OIEC-PT per-batch analysis)

The OIEC-PT per-batch F1 chart (all 4 LLMs, task `ExtrativoOIEC-PT`, evaluated against the OIEC-PT gold with the OIEC-PT rules in the prompt) shows a **synchronized valley at batch 3** (all four models collapse to ~0.07–0.18) and a shared peak at batch 5 (~0.45). Because the swing is synchronized across independently-generated models, it reflects **content difficulty of that batch**, not model behavior. Two mechanisms — the same two that dominate corpus-wide — explain it, and batch 3 concentrates both:

**Mechanism 1 — density of empty-gold (rule S1) sentences = an abstention/precision trap.** Batch 3 has **5 of 10 sentences with empty gold** (vs. 2/10 in batch 5). These are exactly the OIEC-PT rule-S1 "no assertable fact" cases: opinion/evaluation ("Na melhor das hipóteses, é ingênuo…"), imperative ("Vamos simplesmente dizer que ele está errado."), question ("E a posição da Austrália?"), reported speech + hypothetical ("Estamos… à procura de formas possíveis… foi citado."), modal/passive ("…foram também previstas grandes promoções…"). The correct answer on all five is **extract nothing**. The LLMs don't abstain — they extract triples anyway, and every one is a guaranteed false positive, so the batch's precision (and F1) collapses. Corpus-wide, 33 of the 100 OIEC-PT sentences are empty-gold, and ~28–33% of *every* model's triples land on them (all FP).

**Mechanism 2 — structural complexity of the fact-bearing sentences.** The few sentences in batch 3 that *do* have gold require conventions the LLMs rarely reproduce:
- **Appositive-as-copula (E-appos):** "O seu representante…, **Jeff Knott**, declarou:…" → the only gold triple is `(o representante ; é ; Jeff Knott)`. LLMs extract the "declarou…" content and miss the appositive relation.
- **N-ary / coordinated decomposition (E6/E7):** the RSPB sentence carries **4 gold triples** with heavily decomposed, long arg2 ("conflito com muitos líderes conservadores desde o autor da petição Mark Avery ao apresentador de TV Chris Packham"). LLMs almost never reproduce that exact cut.

**Conclusion:** per-batch variance on OIEC-PT is **not random** — it is governed by (1) the proportion of rule-S1 empty-gold sentences (which punishes over-generation) and (2) the structural complexity of the fact-bearing sentences (appositives, n-ary/coordinated relations). Batch 3 is a "perfect storm" of both: 50% non-assertive sentences + extractions that demand appositive and n-ary handling — the two central LLM failure modes (**abstention** and **structural conformity**) co-occurring. 

### 4.8 Per-field (slot) evaluation (`resultados_por_campo.py`)

The all-or-nothing triple match hides *where* a model fails, so a per-slot mode was added: run the same greedy 1-to-1 matcher on **one field at a time** (arg1 vs arg1, rel vs rel, arg2 vs arg2), giving P/R/F1 per slot plus the full-triple reference. Universal pattern across every model and corpus: **arg1 > rel > arg2** (subjects easiest, objects hardest), and every slot F1 ≥ full-triple F1. Two things the triple score masked (BIA):

- **DptOIE** is 2nd on arg1 (0.633) and 2nd on rel (0.504) in DPTO-IE — beating 3 of the 4 LLMs on both — but arg2 collapses (0.290, last), which alone drags its full-triple F1 to last (0.189). Its entire weakness is arg2 (see §4.9).
- **PTOIE-Flair** leads rel (0.529) and full-triple (0.407) in PTOIE-DP even though Claude has higher arg1 (0.650) and arg2 (0.492): PTOIE-Flair's triples **cohere** — the three slots match on the *same* triple more often — while the LLMs get individual slots right but the full combination wrong (over-generation dilutes coherence).

### 4.9 Specialized extractors and the OIEC-PT corpus

**DptOIE (dependency-based).** Two ingestion issues had to be fixed first: (1) it re-tokenizes/de-contracts sentences differently from the gold (`pelos`→`por os`, `na`→`em a`), so its sentences didn't match — fixed by `corrigir_dptoie.py` (contraction-aware + fuzzy remap). (2) ~12% of its triples have **empty arg2** — *by design*: for clausal-complement verbs ("estima que…") it emits a shell `(subj, verb, ∅)` and puts the clause in a separate sub-extraction. Empty-arg2 triples never match → they cap precision. Running DptOIE with all rule flags (`-cc -sc -a -t`) **over-generates** (379→1323 triples) and *lowers* F1 (0.189→0.150); the **default no-flags** config is best. DptOIE is the **most calibrated** model (produces ≈ the gold triple volume) but has the lowest recall.

**PTOIE-Flair (neural, PT-trained).** On OIEC-PT it **dominates**: F1 0.395 (next LLM 0.277), precision 0.506 (>2× any LLM), `sem_match=0`. Trained on PT OIE data, it aligns with the native OIEC-PT annotation conventions the LLMs don't reproduce.

**OIEC-PT scores are compressed and low (F1 ~0.21–0.40)** because of the 33 empty-gold sentences (§4.7): ~30% of every model's triples land there as pure false positives. Crucially, on OIEC the LLMs **drop** vs BIA (Grok 0.45→0.28) while DptOIE **rises** (0.19→0.23) — the generalist↔specialist gap **closes** on the native, strict corpus.

**Data-quality (repeat of §4.4):** Gemini's and gpt5.5's OIEC files arrived in the same flattened/malformed format; `n_pred_sem_match` spiked (Gemini 88) until re-grouped with `corrigir_gemini.py` (needs `python -X utf8` on Windows — its warning `print`s use emoji that crash cp1252). After the fix the scores were **identical**, confirming the flattened items carried no scoreable triples (the malformation was cosmetic, not score-distorting — an earlier over-alarm corrected).

### 4.10 Generalization, the structural-conformity gap, and the `unified` corpus

**Structural-conformity gap.** Even given the OIEC-PT rules in the prompt, the LLMs plateau at ~0.38 F1 on the OIEC-PT task. Near-miss analysis shows they get the **semantics** right but not the **structure** the gold demands. Recurrent divergence types (all penalized by the token matcher): argument granularity (minimal vs extensive, E3/S2), REL/ARG2 boundary (E4), over-inclusion of subordinate clauses (S3), coordination decomposition (E7), contraction handling (E4.1). **Semantic competence ≠ structural conformity** — this validates the manual corpus: SOTA LLMs with the guidelines still can't replicate the annotators' structural decisions.

**Generalization (per-corpus consistency).** PTOIE-Flair holds ~0.40 on both BIA (0.407) and OIEC (0.395); the LLMs are domain-sensitive (Grok 0.45→0.28). A unified leaderboard (DPTO-IE task, both corpora) puts PTOIE-Flair **1st under both** micro (BIA-weighted, 0.404, razor-thin over Grok 0.398) **and** macro (equal-weight per corpus, 0.401 vs Grok 0.363 — clearly ahead). Macro is the fairer "overall" metric (no big corpus dominates), and there the specialist wins decisively — it **generalizes** while the LLMs overfit to the translated/loose corpus.

**The `unified` corpus** (`criar_unified.py`) merges BIA+OIEC (362 sentences), **shuffled with a fixed seed (42)** so each collection batch is a random mix of conventions — the LLM can't infer one convention per batch, giving a clean *mixed-convention generalization* test. Each record keeps a `source` tag (`bia`/`oiec`) so results can be split by origin after the blind collection, and `doc_id` is renumbered sequentially (`orig_doc_id` preserved). Caveat for any write-up: the two rule sets conflict, so no single output can satisfy both perfectly → a built-in ceiling, but identical for all models, so the comparison stays fair.

## 5. Open items / not yet done

- **`corrigir_gemini.py` emoji crash (Windows)**: its warning `print()`s use emoji (⚠️✅❌) that crash under `cp1252`; must be run with `python -X utf8`. Worth swapping the emoji for plain text so it never crashes (same bug already fixed in `gerar_graficos.py`).
- **Unified-corpus collection**: `criar_unified.py` builds the 362-sentence shuffled corpus (registry, batches, `source` tag all ready), but the **LLM responses on it are not yet collected** — re-collection is required because LLM output is prompt-dependent (the specialized extractors just re-run on `dados/unified_sentences.txt`).
- **PTOIE-Flair folder inconsistency**: it sits in `Respostas ExtrativoPTOIE-DP` on BIA but in `Respostas ExtrativoDPTO-IE` on OIEC. Same gold either way (comparison is cross-task), but to put it in the *same* folder as the ptoiedp LLMs it must be moved.
- **Divergence-type quantification** (§4.10): the per-slot near-miss classifier (contraction / REL–ARG2 boundary / granularity / other) exists as a script but is not yet saved/versioned nor run corpus-wide into a table.
- **Groundedness check** (§4.5): designed, not implemented, pending professor approval.
- **Consolidated summary tables** (per-field BIA+OIEC, generalization micro/macro, near-miss types) — computed ad-hoc; not yet assembled into paper-ready artifacts.
- **Path fragility**: scripts still assume cwd = project root (the registry centralizes paths but they remain relative); breaks under IDE "run current file."
- **Previously fixed** (for the record): sentence-misalignment bug (§4.1); coverage bug in `avaliar_condicional` (`graficos_resumo.py`) — an empty-`relations` sentence used to count as "covered", inflating coverage to 100% (e.g. PTOIE-Flair's real coverage is ~81%); `gerar_graficos.py` emoji crash; `checagem_consenso.py` duplicate `__main__` block.
