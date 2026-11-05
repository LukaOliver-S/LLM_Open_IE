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
- `--k`: (optional, default `1`) which repetition round this collection is. `k=1` writes
  to the usual paths (fully backward-compatible with everything below); `k>=1` writes
  into an isolated `k{N}/` sibling folder inside `<N>_batches/`, so repeated collections
  of the same model/task never overwrite each other or the original run. Used to measure
  generation variance — see `variancia_geracao.py` below.
- `--forcar`: overwrite the final `.jsonl` even if it already exists with different content
  (normally refused, to avoid silently clobbering a manual collection by accident).

Because `--corpus` routes responses straight into `Respostas/<corpus>/`, collected files
already land where the evaluation expects them — no manual moving needed.

Shared prompt-assembly and file-layout logic (`TAREFAS`, `montar_texto`, `pasta_rodada`,
`reconstruir_arquivo_final`, `escrever_protegido`) lives in `scripts/formatacao/_coleta_comum.py`,
so any future collection script (manual or scripted) can reuse the exact same conventions.

#### 2b. Local extraction with Portuguese-OpenIE models (Colab/Kaggle)

In addition to the chat-collected commercial LLMs, the pipeline has been evaluated against
open-weight, Portuguese-native extractors from the
[Portuguese-OpenIE](https://github.com/FORMAS/Portuguese-OpenIE) library — `Qwen3OIE`
(0.6B/4B/8B), `PortugueseT5OIE` (+ an abstractive variant), `LlamaPortOIE3`, and `PortNOIE`.
Unlike the chat LLMs, these models take **no task-specific prompt** — `extract(sentence)` is
fixed per model, and (for the transformers backend) fully **deterministic** (`do_sample=False`
internally), so there's no generation variance to measure for them and no `--k` repetition step.

This runs outside the repo, in a Colab or Kaggle notebook with GPU access (`pip install
"portuguese-openie[all]"`), since it needs `transformers`/`torch` with CUDA rather than this
project's own lightweight `requirements.txt`. The notebook clones this repo, runs every sentence
in `sentencas/<N>_sentencas/` (or `sentencas_oiecpt/`) through each model, and writes output in
the pipeline's own JSONL schema to a staging folder:

```
Respostas/<corpus>/<N>_batches/_extratores_locais/<Modelo>.jsonl
```

Because these models score against the **same single gold file per corpus** regardless of task
(there's no prompt to vary), a single extraction run is reused across all three extractive task
tables for direct comparison against the chat-LLM prompt variants — copy the same file into each
categoria folder (`Respostas ExtrativoDPTO-IE`, `OIEC-PT`, `PTOIE-DP`), and the abstractive
variant into `Respostas AbstractiveOpenIE`. This is a deliberate copy, not a re-run: the
prediction doesn't change per task, only which gold-comparison table it shows up in.

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

#### CaRB scoring and generation-variance guardrails (`scripts/Validacao/carb_score.py` et al.)

A separate, PT-adapted port of the [CaRB](https://aclanthology.org/D19-1651/) scorer (see
`Guardrails.md` for the full methodology and rationale):

```bash
python scripts/Validacao/rodar_carb.py --corpus bia --tarefa oiec [--ic]
```

- `--tarefa`: `abstractive`, `dpto`, `oiec`, or `ptoiedp`.
- `--ic`: bootstrap 95% confidence intervals (error bars on the plot).

Scores every `*.jsonl` file found in the corresponding categoria folder and writes
`Outputs/metricas/<corpus>/carb/carb_<corpus>_<tarefa>.csv` + a matching `.png`.

**Generation variance + consensus**, for models collected across multiple `--k` rounds
(see `assistente_coleta.py --k` above):

```bash
python scripts/Validacao/variancia_geracao.py --corpus bia --tarefa oiec --modelo <NomeDoModelo> --lotes <N> --k <K>
```

Walks `k=1..K` via the same `pasta_rodada` convention, reports each round's F1, the
mean ± standard deviation across rounds (the actual measured generation variance, as opposed
to citing literature figures), and a **consensus** F1 — a per-sentence majority-vote across the
k predicted triple sets, which typically outperforms the single-round mean. Writes
`Outputs/metricas/<corpus>/carb/variancia_<tarefa>_<modelo>.csv`.


## Métricas de grafos das triplas

O script `scripts/graphs/metrics_graph.py` transforma as triplas (arg1, rel, arg2) em grafos e calcula as métricas de teoria dos grafos vistas na aula. Cada tripla vira uma aresta entre arg1 e arg2. Nas métricas a direção é ignorada, e laços e triplas incompletas são descartados. Os vértices são o texto do argumento em minúsculas, com espaços normalizados.

### Requisitos

```bash
pip install networkx
```

(inclua `networkx` no `requirements.txt` se ainda não estiver lá)

### Configuração

No topo do script, em `CONFIGURAÇÃO`:

| Variável | O que é |
|---|---|
| `DADOS` | pasta que contém `dados/` (gold) e `Respostas/` (extrações). Os dados são lidos daqui |
| `SAIDA_PADRAO` | pasta onde os resultados são gravados. Padrão: `Outputs/graphs/metrics` |
| `CORPORA` | corpora conhecidos: `oiec_pt`, `bia`, `unified` |

As pastas de saída são criadas automaticamente se não existirem.

### Como rodar

Abra o terminal na pasta `scripts/graphs` e use:

```bash
python metrics_graph.py                 # gold e todas as extrações, de todos os corpora
python metrics_graph.py gold            # só os corpora gold
python metrics_graph.py extracoes       # só as extrações
python metrics_graph.py comparar        # compara cada extrator com o gold, só nas sentenças em comum
python metrics_graph.py comparar oiec_pt
python metrics_graph.py bia gold        # filtros por corpus podem ser combinados com gold, extracoes e comparar
```

Também aceita um caminho de arquivo `.jsonl` ou de pasta, e `--saida` para mudar a pasta de resultados:

```bash
python metrics_graph.py "caminho/para/pasta_ou_arquivo" --saida "outra/pasta"
```

Pastas de extrações que começam com `_` (por exemplo `_bruto`) são ignoradas.

### Formatos de entrada aceitos

- Extrações: `{"sentence": "...", "relations": [{"arg1": ..., "rel": ..., "arg2": ...}]}`
- Gold: `{"sentence": "...", "gold": [{"arg1": ..., "rel": ..., "arg2": ..., "valid": true}]}`. Triplas com `valid: false` são ignoradas
- Um objeto por linha (JSONL) ou arrays JSON indentados, um depois do outro (alguns arquivos de resposta vêm assim). Trechos inválidos são pulados, com um aviso por arquivo

### Saída

```
Outputs/graphs/metrics/
└── <corpus>/                          oiec_pt, bia ou unified
    ├── gold/
    │   ├── metricas_corpus.csv
    │   └── metricas_sentencas.csv
    └── <pasta das extrações>/         por exemplo 10_batches/Respostas ExtrativoOIEC-PT
        ├── metricas_corpus.csv
        ├── metricas_sentencas.csv
        └── comparacao_gold.csv        só com o comando comparar
```

`metricas_sentencas.csv` traz uma linha por sentença: `n` (vértices), `m` (arestas), `grau_max`, `componentes`, `conexo`, `formato` (estrela, arvore, com ciclo ou desconexo), `pontes`, `articulacoes`, `diametro`, `triangulos`, `nu` (emparelhamento máximo), `tau` (cobertura de vértices mínima), `alfa` (conjunto independente máximo, igual a n − τ) e `rho` (cobertura de arestas mínima, igual a n − ν).

`metricas_corpus.csv` traz uma linha por arquivo, com o grafo de todas as sentenças juntas: vértices, arestas, densidade, componentes, fração do maior componente, grau médio e máximo, pontes, articulações, diâmetro do maior componente, agrupamento, transitividade, limites para τ e α, e os 5 vértices de maior grau, intermediação e proximidade.

`comparacao_gold.csv` traz uma linha por extrator, usando só as sentenças que têm triplas no gold e na resposta (casadas pelo texto da sentença). Cada métrica aparece nas versões `_gold` e `_resp`: vértices, arestas e a proporção de cada formato. Há ainda `mesma_forma` (fração de sentenças em que as duas formas coincidem), `mesmo_n_vertices` e `dif_arestas_media` (resposta menos gold).

### Cuidados na leitura

- As métricas descrevem a forma do grafo, não se as triplas estão corretas. Para isso use as métricas de precisão e revocação em `Outputs/metricas`.
- No grafo do corpus, vértices de sentenças diferentes com o mesmo texto são fundidos. Pronomes como "ele" e "isso" viram hubs por causa disso, e não por importância real. As métricas por sentença não têm esse efeito.
- A cobertura de vértices mínima (τ) é NP-difícil. Por sentença é calculada exatamente, até 18 vértices. No grafo do corpus aparece só como intervalo, ν ≤ τ ≤ 2ν.
- A intermediação do corpus é normalizada e calculada com uma amostra de até 300 vértices. O diâmetro é exato até 1500 vértices no maior componente, e acima disso é um limite inferior.
- Nas pastas `k2` a `k6` há poucas sentenças em comum com o gold em alguns extratores, então não compare essas pastas entre si.