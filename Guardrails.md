# Guardrails para Avaliação de LLMs em OpenIE (PT-BR)

> Catálogo de salvaguardas metodológicas para o estudo comparativo LLMs vs.
> extratores especializados (PTOIE-Flair, DptOIE) em Open Information Extraction
> no português. Organizado por categoria, com viabilidade no **cenário real do
> projeto** (interfaces de chat gratuitas, sem API/seed/temperature).

**Legenda de viabilidade:** ✅ viável · ⚠️ parcial/custa coleta manual · ❌ requer API (fora do escopo)

---

## 1. Motivação

LLMs são modelos **generativos e estocásticos**: a mesma entrada pode gerar
saídas diferentes a cada execução. Isso ameaça a validade de uma comparação
baseada numa **única** coleta. Os *guardrails* abaixo são maneiras de **controlar,
medir ou reduzir** esse e outros ruídos — transformando "as LLMs variam, e agora?"
em decisões metodológicas declaradas.

## 2. Duas fontes de variância (não confundir)

| Fonte | O que é | Ferramenta correta |
|---|---|---|
| **Geração** (estocasticidade da LLM) | re-perguntar → resposta diferente | **k rodadas + consenso** |
| **Amostragem** (corpus finito) | quais frases caíram no corpus | **bootstrap** |

> ⚠️ O **bootstrap NÃO resolve** a estocasticidade da LLM — ele reamostra as
> mesmas respostas já coletadas. São eixos ortogonais; o artigo deve tratar os dois.

## 3. Restrição do setup: chat vs. API

O controle de amostragem (`temperature`, `seed`) **só existe via API**, cobrada por
token. As **interfaces conversacionais** (gratuitas **e** pagas — ChatGPT Plus,
Claude Pro) **não** expõem esses parâmetros. Como o estudo usa apenas as interfaces
gratuitas, a reprodutibilidade não é controlável — daí a necessidade de **medir** a
variância em vez de fixá-la.

- Mesmo via API, a reprodutibilidade **não é garantida**: Claude não tem `seed`;
  Gemini apresenta não-determinismo mesmo com `seed` fixo; todos documentam que
  `temperature=0` dá apenas *quase*-determinismo.

Fontes: [OpenAI seed](https://developers.openai.com/cookbook/examples/reproducible_outputs_with_the_seed_parameter) ·
[Consistência LLM 2025](https://www.keywordsai.co/blog/llm_consistency_2025) ·
[Gemini não-determinismo](https://discuss.ai.google.dev/t/the-gemini-api-is-exhibiting-non-deterministic-behavior-for-the-gemini-2-5-pro-model-it-is-producing-different-outputs-for-identical-requests-even-when-a-fixed-seed-is-provided-along-with-a-constant-temperature-this-behavior-has-been-reliably-rep/101331) ·
[Chat vs API](https://www.aipricing.guru/subscription-vs-api/)

---

## 4. Catálogo de guardrails

### A. Prompt

| Guardrail | O que é / por quê | Viável | Fonte |
|---|---|---|---|
| **Sensibilidade ao prompt** | Rodar variações (parafrasear, mudar pontuação/formatação, reordenar) e medir a oscilação do F1. LLMs variam **até 76 pontos** só por formatação. | ⚠️ | [Sclar et al.](https://openreview.net/forum?id=RIu5lyNXjT), [ProSA](https://arxiv.org/pdf/2410.12405) |
| **Few-shot + ordem dos exemplos** | Exemplos reduzem a sensibilidade; mas a *ordem* deles afeta (viés recência/primazia). | ⚠️ | [The Order Effect](https://arxiv.org/html/2502.04134v2) |
| **Reforço de formato** | Especificar rigidamente o JSON de saída. | ✅ **já aplicado** (`FORMATO_REFORCO`) | [Single Character](https://arxiv.org/pdf/2510.05152) |
| **Prompt fixo + divulgado** | Reportar prompt exato, versão do modelo e data da coleta. | ✅ | — |

### B. Geração / amostragem (cerne da estocasticidade)

| Guardrail | O que é / por quê | Viável | Fonte |
|---|---|---|---|
| **k rodadas + variância** | Rodar k vezes; reportar **média ± desvio**. Variância intra-modelo pode explicar **10–34%** da variância total. | ⚠️ | [LLM Stability](https://arxiv.org/pdf/2408.04667v2), [Within vs Between](https://arxiv.org/pdf/2601.21339) |
| **Self-consistency / consenso** | Agregar as k saídas por **voto majoritário** → afoga erros esporádicos (+12–18% em benchmarks). | ⚠️ | [Self-consistency](https://learnprompting.org/docs/intermediate/self_consistency) |
| **Greedy / temperatura 0** | Decodificação determinística. | ❌ só-API | [Reproducible Eval](https://arxiv.org/pdf/2405.14782) |

### C. Formato / validação de saída

| Guardrail | O que é / por quê | Viável | Fonte |
|---|---|---|---|
| **Validação de esquema** | JSON válido, `relations` presente, tipos certos. Modo JSON solto falha **5–10%** (foi o bug do Gemini). | ✅ pós-processamento | [Structured outputs](https://agenta.ai/blog/the-guide-to-structured-outputs-and-function-calling-with-llms) |
| **Grounding (extrativo)** | Todo token de arg1/rel/arg2 existe na frase. | ✅ | — |
| **Contagem/alinhamento** | 1 saída por frase; sem fundir sentenças. | ✅ | — |
| **Constrained decoding / schema nativo** | Força 100% de conformidade. | ❌ só-API | [Reliability](https://arxiv.org/pdf/2605.02363) |

### D. Medição / estatística

| Guardrail | O que é / por quê | Viável | Fonte |
|---|---|---|---|
| **Bootstrap pareado + IC** | IC 95% e p-valor da diferença entre sistemas (1000+ reamostragens). | ✅ **já implementado** | [Dror et al.](https://www.semanticscholar.org/paper/The-Hitchhiker%E2%80%99s-Guide-to-Testing-Statistical-in-Dror-Baumer/d10df96b3fb0ab5c6b1d0cc22c7400d0acccc3cc) |
| **Componentes de variância** | Reportar as duas fontes (amostragem + geração) separadamente. | ✅ | [Within vs Between](https://arxiv.org/pdf/2601.21339) |
| **Múltiplas métricas** | Não depender de um scorer só (CaRB + matcher próprio + por-campo). | ✅ já têm | — |

### E. Validade (o que revisor vai atacar)

| Guardrail | O que é / por quê | Viável | Fonte |
|---|---|---|---|
| **⚠️ Contaminação / vazamento** | LLM pode ter visto o corpus no treino → F1 inflado. Contaminação chega a **45–92%** em benchmarks. **BIA é de Wikipédia** → risco alto. No mínimo **declarar**; idealmente teste de memorização (prefixo→sufixo, n-gram). | ✅ declarar / ⚠️ detectar | [Awesome Data Contamination](https://github.com/lyy1994/awesome-data-contamination), [Contamination-Resistant](https://arxiv.org/html/2605.19999v1) |
| **Coleta cega e consistente** | Mesmo prompt, mesma janela temporal, corpus fixo e versionado. | ✅ | — |
| **Validação humana de amostra** | Conferir manualmente N extrações pra calibrar o scorer automático. | ✅ | — |

---

## 5. Priorização para o artigo

1. **k rodadas + consenso** (B) — responde diretamente à estocasticidade. **Prioridade 1.**
2. **⚠️ Contaminação de dados** (E) — barato e blinda contra a pergunta "o modelo já viu o corpus?". **Prioridade 1.**
3. **Validação de saída** (C) — quantifica a "obediência" de cada LLM (formato, grounding). **Prioridade 2.**
4. **Sensibilidade ao prompt** (A) — forte, mas cara (mais coleta). **Prioridade 3 / opcional.**
5. **Bootstrap** (D) — **já pronto**, camada de significância. Coadjuvante.

Os itens ❌ (constrained decoding, temp=0, seed) ficam **fora** por serem só-API — o que, por si, vira uma **limitação declarada**.

---

## 6. Status de implementação (neste repositório)

| Item | Status | Onde |
|---|---|---|
| Scorer **CaRB** (fiel, PT, casos especiais desligáveis) | ✅ | `scripts/Validacao/carb_score.py` |
| **Bootstrap** pareado + IC + p-valor | ✅ | `scripts/Validacao/bootstrap_carb.py` |
| Runner + gráfico (F1 + IC) | ✅ | `scripts/Validacao/rodar_carb.py` |
| Loader robusto (JSONL / arrays concatenados) | ✅ | `bootstrap_carb.py::carregar_jsonl` |
| **k rodadas + consenso** | ⬜ pendente | — |
| **Teste de contaminação** | ⬜ pendente | — |
| **Validação de saída (guardrails.py)** | ⬜ esboçado | — |

---

## 7. Frases prontas para a metodologia

- **Setup:** "As LLMs foram acessadas por suas interfaces conversacionais, que não
  expõem parâmetros de amostragem (`temperature`/`seed`) — nem em planos gratuitos
  nem pagos; tais controles existem apenas via API. Como não usamos a API, a
  variabilidade de geração não é controlável e a quantificamos empiricamente."

- **Estocasticidade:** "Adotamos salvaguardas estatísticas: (i) reamostragem
  *bootstrap* para intervalos de confiança e teste pareado entre sistemas;
  (ii) repetição de k execuções em um subconjunto para quantificar a variância de
  geração; (iii) agregação por consenso para reduzi-la. Comparações são reportadas
  com IC, não como pontos únicos."

- **Contaminação:** "Reconhecemos o risco de contaminação: parte do corpus deriva de
  fontes públicas (Wikipédia) possivelmente presentes no treino das LLMs. [Reportamos
  um teste de memorização prefixo→sufixo / declaramos a limitação.]"

- **Métrica:** "Usamos a correspondência lexical token-level do CaRB. As relaxações
  específicas do inglês (cópula *be*; inversão de argumentos em verbos de dizer) foram
  desativadas para transparência em português; ativá-las altera o F1 em <0,007 e não
  modifica nenhum ordenamento entre sistemas."

---

## 8. Referências

- Bhardwaj, Aggarwal, Mausam. **CaRB: A Crowdsourced Benchmark for Open IE.** EMNLP-IJCNLP 2019. [aclanthology.org/D19-1651](https://aclanthology.org/D19-1651/)
- Atil et al. **LLM Stability.** [arXiv:2408.04667](https://arxiv.org/pdf/2408.04667v2)
- Biderman et al. **Lessons from the Trenches on Reproducible Evaluation of Language Models.** [arXiv:2405.14782](https://arxiv.org/pdf/2405.14782)
- Sclar et al. **Quantifying Language Models' Sensitivity to Spurious Features in Prompt Design.** [OpenReview](https://openreview.net/forum?id=RIu5lyNXjT)
- **ProSA: Assessing and Understanding the Prompt Sensitivity of LLMs.** [arXiv:2410.12405](https://arxiv.org/pdf/2410.12405)
- **The Order Effect: Prompt Sensitivity to Input Order.** [arXiv:2502.04134](https://arxiv.org/html/2502.04134v2)
- Wang et al. **Self-Consistency Improves Chain of Thought Reasoning.** [learnprompting](https://learnprompting.org/docs/intermediate/self_consistency)
- Dror et al. **The Hitchhiker's Guide to Testing Statistical Significance in NLP.** [Semantic Scholar](https://www.semanticscholar.org/paper/The-Hitchhiker%E2%80%99s-Guide-to-Testing-Statistical-in-Dror-Baumer/d10df96b3fb0ab5c6b1d0cc22c7400d0acccc3cc)
- **Awesome Data Contamination** (lista de papers). [GitHub](https://github.com/lyy1994/awesome-data-contamination)
- **LLM Benchmark Datasets Should Be Contamination-Resistant.** [arXiv:2605.19999](https://arxiv.org/html/2605.19999v1)
</content>
