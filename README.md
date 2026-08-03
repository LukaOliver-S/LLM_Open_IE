# LLM_Open_IE

A pipeline for Open Information Extraction (Open IE) in Portuguese using large language models. Given a sentence, it extracts relational triples ⟨ARG1, REL, ARG2⟩ that encode the factual propositions expressed in the text, without relying on predefined domains or ontologies.

The extraction is guided by explicit structural and semantic rules (grounded in the OIEC-PT, DPTO-IE and Abstractive-Bruno annotation methodology), so the LLM produces triples that stay faithful to the sentence rather than inventing facts. The pipeline runs sentences through rule-encoded prompts, parses the model's output into structured triples, and validates them against the rules.

## Running the pipeline

All commands must be run from the project root (`LLM_Open_IE/`), regardless of which
folder the script lives in — the scripts resolve paths relative to the project root, not
to their own location.

### 1. Data preparation (`scripts/formatacao/`)

Extract plain sentences from the gold file, then split them into batches:

```bash
python scripts/formatacao/scriptFormatador.py
python scripts/formatacao/dividir.py
```

`dividir.py`'s batch size is set by the `numero_de_partes` variable at the top of the
file — edit it before running to generate a new `sentencas/<N>_sentencas/` folder.

If a model's raw output comes in a broken/flattened format (as Gemini sometimes does),
fix it with:

```bash
python scripts/formatacao/corrigir_gemini.py <arquivo_bruto.jsonl> [saida.jsonl] [--gold dados/bia_gold_sentences.jsonl]
```

The dependency-based extractor **DptOIE** needs its own fixers — its sentences
re-tokenize/de-contract (e.g. `pelos` → `por os`), and its JSON output uses
`extractions`/`sub_extractions` instead of `relations`:

```bash
# align DptOIE sentences to the gold (fuzzy + contraction-aware remap)
python scripts/formatacao/corrigir_dptoie.py <arquivo.jsonl> [saida.jsonl] --gold dados/bia_gold_sentences.jsonl

# convert DptOIE JSON output (-ot json) into the pipeline's JSONL (extractions -> relations,
# rebuilding empty arg2 from sub_extractions)
python scripts/formatacao/converter_dptoie_json.py <arquivo.json> [saida.jsonl] --gold dados/bia_gold_sentences.jsonl
```

### 2. Collecting model responses (`scripts/formatacao/assistente_coleta.py`)

Semi-automated helper: copies each batch's prompt to the clipboard, waits for you to
paste the model's reply, and saves it in the right place. Resumable — safe to stop and
rerun later.

```bash
python scripts/formatacao/assistente_coleta.py --corpus bia --tarefa abstractive --modelo <NomeDoModelo> --lotes <N>
python scripts/formatacao/assistente_coleta.py --corpus bia --tarefa dpto         --modelo <NomeDoModelo> --lotes <N>
python scripts/formatacao/assistente_coleta.py --corpus bia --tarefa oiec         --modelo <NomeDoModelo> --lotes <N>
```

- `--corpus`: `bia` (default) or `oiec_pt` — sets **both** where the batches are read from
  and where responses are saved, matching the evaluation (`oiec_pt` reads `sentencas_oiecpt/`
  and saves under `Respostas/oiec_pt/`). Override each folder individually with
  `--sentencas-base` / `--respostas-base` if you ever need to.
- `--tarefa`: `abstractive`, `dpto`, `oiec`, or `ptoiedp`
- `--modelo`: any name (becomes the output filename, e.g. `Claude_Sonnet5`)
- `--lotes`: batch size to use (must match an existing `<sentencas-base>/<N>_sentencas/` folder)
- `--apenas-lotes 3,7,12`: (optional) re-collect only specific batch numbers instead of all

Because `--corpus` routes responses straight into `Respostas/<corpus>/`, collected files
already land where the evaluation expects them — no manual moving needed.

### 3. Evaluation (`scripts/Validacao/`)

**Corpora.** The pipeline evaluates one corpus at a time, chosen with `--corpus`
(default `bia`). Each corpus has its **own gold, response folder and output folder**,
so results from different corpora never mix:

| corpus | gold | responses | outputs |
|---|---|---|---|
| `bia` (default) | `dados/bia_gold_sentences.jsonl` | `Respostas/bia/` | `Outputs/metricas/bia/` |
| `oiec_pt` | `dados/oiec_pt_gold_sentences.jsonl` | `Respostas/oiec_pt/` | `Outputs/metricas/oiec_pt/` |

To add a corpus, edit the `CORPORA` dict at the top of `resultados.py` — every script
imports it from there.

Run in this order (shown for `--corpus bia`; swap to `--corpus oiec_pt` for the other).
Each script auto-discovers every `Respostas/<corpus>/<N>_batches/Respostas */` folder:

```bash
python scripts/Validacao/resultados.py --corpus bia
python scripts/Validacao/resultados_por_campo.py --corpus bia --lotes <N>
python scripts/Validacao/comparação_batches.py --corpus bia --lotes <N>
python scripts/Validacao/contagem_triplas.py --corpus bia --lotes <N>
python scripts/Validacao/graficos_resumo.py --corpus bia --lotes <N>
python scripts/Validacao/checagem_consenso.py --corpus bia --lotes <N>
python scripts/Validacao/gerar_graficos.py Outputs/metricas/bia/<N>_batches/resultados_Respostas_AbstractiveOpenIE.csv Outputs/metricas/bia/<N>_batches/resultados_Respostas_ExtrativoDPTO-IE.csv Outputs/metricas/bia/<N>_batches/resultados_Respostas_ExtrativoOIEC-PT.csv Outputs/metricas/bia/<N>_batches/resultados_Respostas_ExtrativoPTOIE-DP.csv
```

- `--corpus`: `bia` (default) or `oiec_pt`; omit it to use `bia`.
- `--lotes <N>`: optional filter for a single batch size — omit to process every batch
  size found. `resultados.py` always processes all batch sizes; `gerar_graficos.py`
  takes explicit CSV paths instead (point them at the corpus's output folder).

| Script | What it produces | Where (under the corpus's output folder) |
|---|---|---|
| `resultados.py` | Precision/recall/F1 (lexical + exact) per model per task | `resultados_Respostas_*.csv` |
| `resultados_por_campo.py` | P/R/F1 **per slot** (arg1/rel/arg2) + grouped-bar chart | `resultados_por_campo_*.csv`, `grafico_por_campo_*` |
| `comparação_batches.py` | Same metrics, broken down per original batch | `por_batch/` |
| `contagem_triplas.py` | Gold vs. predicted triple volume (over/under-generation) | `graficos_triplas/` |
| `graficos_resumo.py` | Coverage vs. quality, precision×recall scatter | `graficos_resumo/` |
| `checagem_consenso.py` | Cross-model agreement on false positives | `consenso/` |
| `gerar_graficos.py` | Paper-ready charts from `resultados_*.csv` | `graficos_lexical/` |

All outputs land under `Outputs/metricas/<corpus>/<N>_batches/`.
