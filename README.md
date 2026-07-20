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

### 2. Collecting model responses (`scripts/formatacao/assistente_coleta.py`)

Semi-automated helper: copies each batch's prompt to the clipboard, waits for you to
paste the model's reply, and saves it in the right place. Resumable — safe to stop and
rerun later.

```bash
python scripts/formatacao/assistente_coleta.py --tarefa abstractive --modelo <NomeDoModelo> --lotes <N>
python scripts/formatacao/assistente_coleta.py --tarefa dpto         --modelo <NomeDoModelo> --lotes <N>
python scripts/formatacao/assistente_coleta.py --tarefa oiec         --modelo <NomeDoModelo> --lotes <N>
```

- `--tarefa`: `abstractive`, `dpto`, or `oiec`
- `--modelo`: any name (becomes the output filename, e.g. `Claude_Sonnet5`)
- `--lotes`: batch size to use (must match an existing `sentencas/<N>_sentencas/` folder)
- `--apenas-lotes 3,7,12`: (optional) re-collect only specific batch numbers instead of all

### 3. Evaluation (`scripts/Validacao/`)

Run in this order. Each auto-discovers every `Respostas/<N>_batches/Respostas */` folder
(no arguments needed), except the last one:

```bash
python scripts/Validacao/resultados.py
python scripts/Validacao/comparação_batches.py --lotes <N>
python scripts/Validacao/contagem_triplas.py --lotes <N>
python scripts/Validacao/graficos_resumo.py --lotes <N>
python scripts/Validacao/checagem_consenso.py --lotes <N>
python scripts/Validacao/gerar_graficos.py Outputs/metricas/<N>_batches/resultados_Respostas_AbstractiveOpenIE.csv Outputs/metricas/<N>_batches/resultados_Respostas_ExtrativoDPTO-IE.csv Outputs/metricas/<N>_batches/resultados_Respostas_ExtrativoOIEC-PT.csv
```

`--lotes <N>` is optional on all but `resultados.py` (not yet supported there) and
`gerar_graficos.py` (takes explicit CSV paths instead) — omit it to process every batch
size found under `Respostas/`.

| Script | What it produces | Where |
|---|---|---|
| `resultados.py` | Precision/recall/F1 (lexical + exact) per model per task | `resultados_Respostas_*.csv` |
| `comparação_batches.py` | Same metrics, broken down per original batch | `por_batch/` |
| `contagem_triplas.py` | Gold vs. predicted triple volume (over/under-generation) | `graficos_triplas/` |
| `graficos_resumo.py` | Coverage vs. quality, precision×recall scatter | `graficos_resumo/` |
| `checagem_consenso.py` | Cross-model agreement on false positives | `consenso/` |
| `gerar_graficos.py` | Paper-ready charts from `resultados_*.csv` | `graficos_lexical/` |

All outputs land under `Outputs/metricas/<N>_batches/`.
