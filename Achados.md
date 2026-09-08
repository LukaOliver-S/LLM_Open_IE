# Achados — OpenIE em Português (LLMs vs. Extratores Especializados)

> Síntese **qualitativa** de tudo que descobrimos. Sem números aqui — só os
> achados, as explicações e o que cada um significa. As métricas estão nos
> CSVs/gráficos em `Outputs/metricas/` e nos slides.

---

## 1. Achado central: o especializado vence — mas **por precisão**

O extrator especializado **neural** (PTOIE-Flair) supera as LLMs na tarefa de
extração — mas **não por recuperar mais fatos**, e sim por ser **preciso**.

- **PTOIE-Flair = cirúrgico:** extrai **poucas** triplas, mas quase todas certas.
  Precisão altíssima, recall menor.
- **LLMs = exaustivas:** recuperam **muitos** fatos (recall alto), mas
  **super-geram** — despejam triplas demais, longas e imprecisas → precisão baixa.

Essa oposição **precisão vs. recall** é a história mais forte do trabalho, e
aparece de forma consistente em todos os modelos e corpora.

## 2. Especializado de **regras** ≠ especializado **neural**

A hipótese "especializado > LLM" **só se confirma para o modelo neural**:

- O **PTOIE-Flair (neural)** ganha das LLMs onde atua.
- O **DptOIE (baseado em regras)** **NÃO** ganha — a melhor LLM (Grok) empata ou
  supera ele.
- Conclusão: não é "especializado" que vence, é **especializado neural bem
  finalizado**. Regras não bastam.

## 3. A vantagem do especializado **cresce na dificuldade**

Quando as frases ficam difíceis (lotes mais complexos), as **LLMs colapsam**
(super-geram lixo e a precisão despenca), mas o **PTOIE-Flair segura** — a
precisão o mantém à tona. Ou seja: quanto mais difícil a frase, **maior** a
vantagem do especializado. Nos casos fáceis, os dois se aproximam.

## 4. Grok é a LLM mais forte

Entre as LLMs, o **Grok** se destaca — lidera a maioria das tarefas e é a única
que chega a bater o especializado de regras. Tem a **melhor precisão** entre as
LLMs mantendo recall alto. As outras (Claude, Gemini, GPT) se separam pouco entre
si (e frequentemente de forma **não-significativa**).

## 5. **A métrica muda a força da conclusão**

- O **CaRB** dá **crédito parcial** (palavra a palavra) e tem uma agregação que
  é **generosa com as LLMs verbosas**.
- O **matcher lexical por campo** (mais rígido) **favorece mais o especializado**.
- Ou seja: **quanto mais rígida a métrica, mais o especializado ganha.** Vale
  reportar as duas — a conclusão depende de como se mede.

## 6. Variabilidade e significância — o ponto que exige cuidado

- **A dificuldade varia MUITO entre lotes** (algumas dezenas de frases), e
  **todos os modelos sobem e descem juntos** → a dificuldade é **intrínseca às
  frases**, não do modelo. Qual frase caiu no corpus importa mais do que qual
  modelo você usou.
- Como o corpus é pequeno e heterogêneo, um **número único é frágil**. Por isso
  usamos **bootstrap** (intervalos de confiança).
- **⚠️ Correção (o teste certo é o pareado, não a sobreposição visual dos ICs):**
  na primeira leitura, os ICs marginais do PTOIE-Flair e do concorrente mais
  próximo pareciam se tocar nos dois corpora — e eu concluí (errado) que o
  OIEC-PT seria "não-significativo". Rodando o **teste pareado de verdade**
  (mesmas reamostragens do bootstrap para os dois modelos, o que cancela
  ruído compartilhado), o resultado é **significativo (p&lt;0,05) nos DOIS
  corpora**: no BIA contra todas as LLMs (a mais próxima, Claude, p≈0,025); no
  OIEC-PT também contra todas (a mais próxima, Grok, p≈0,031). A vantagem do
  PTOIE-Flair é mais **apertada** no OIEC-PT (corpus menor, IC mais largo),
  mas não é inconclusiva. Ver §14 para o detalhamento.
- ⚠️ O bootstrap mede a incerteza de **quais frases** caíram (amostragem), **não**
  a incerteza de **re-perguntar à LLM** (geração). São duas coisas diferentes.

---

## 7. OIEC-PT em detalhe

- **O OIEC-PT é mais difícil que o BIA** em quase tudo. Motivos: as
  regras de **factualidade (S1)** deixam muitas frases com **gold vazio**, o
  corpus tem **contrações** (convenção diferente do BIA, que é descontraído), e as
  frases tendem a ser mais complexas. Detalhamento quantificado (razão de
  triplas, % de consenso, largura de IC, gap por dificuldade): **ver §14**.
- **É pequeno e heterogêneo** → intervalos largos, resultados **não-significativos**.
  É o principal motivo pra a hipótese não fechar com força ali.
- **Há um lote patológico** onde **nenhum modelo** acerta uma única tripla exata —
  frases muito difíceis (provavelmente gold vazio / muito complexas). Todos
  afundam juntos.
- Padrão de tarefa no OIEC: o especializado de regras leva a melhor na tarefa
  "DptOIE" por muito pouco; uma LLM lidera a tarefa "OIEC"; o PTOIE-Flair lidera a
  tarefa "PTOIE" (mas sem significância).

---

## 8. Reprodutibilidade e o setup (LLMs via chat)

- **As interfaces de chat não expõem `temperature` nem `seed`** — nem nos planos
  gratuitos **nem nos pagos** (Plus/Pro). Esses controles só existem na **API**.
- Como o estudo usa **as interfaces (não a API)**, a **estocasticidade das LLMs é
  incontrolável** — a resposta pode mudar a cada rodada e não há como fixar.
- Mesmo se fôssemos pra API, **reprodutibilidade exata não é garantida**: o Claude
  não tem `seed`, o Gemini é não-determinístico mesmo com `seed`, e todos só
  prometem *quase*-determinismo com `temperature=0`.
- Isso vira uma **decisão metodológica declarada**: em vez de fixar a variância,
  a gente **mede** (bootstrap; e, idealmente, k rodadas).

### Guardrails que levantamos (catálogo)
- **Prompt:** sensibilidade a formatação/ordem; few-shot reduz a variação.
- **Geração:** k rodadas (medir a variância) + consenso (reduzi-la).
- **Formato:** validar o JSON de saída, checar *grounding*.
- **Estatística:** bootstrap (já feito) + teste pareado.
- **Validade:** ⚠️ **contaminação de dados** — o BIA é de Wikipédia, então as LLMs
  podem ter visto o corpus no treino (F1 inflado). No mínimo, **declarar**.

---

## 9. dptoie-neural (FORMAS) — por que **não deu** para incluir

- É um OIE **neural** legítimo da FORMAS, seria um segundo baseline neural.
- **Impossível de rodar hoje:** o modelo pré-treinado depende de **embeddings
  Flair-"diários"** hospedados num servidor que agora dá **403** (sumiu). A
  alternativa (re-treinar com BERTimbau) esbarra na **stack de 2022**: o
  `allennlp 2.7` exige uma versão antiga do `torch` que **não tem mais instalação**
  em Python/plataforma atual. É **irreproduzível**.
- Além disso, o próprio repo indica que o modelo é **imaturo** (a avaliação
  interna dele é quase-zero e "suporte a BERT" era um item **a fazer**).
- **Encerrado.** Única rota real: **pedir à FORMAS** que rodem no ambiente
  original e enviem as extrações. O **PTOIE-Flair** já cobre o slot
  "especializado-neural".

---

## 10. Qualidade dos dados — problemas encontrados (e o que fizemos)

- **Gemini (e em parte o GPT) salvam a saída como vários *arrays* JSON
  concatenados**, não como JSONL. Um leitor linha-a-linha recupera **zero** e
  falha silenciosamente. (Sintoma no CaRB: precisão 1.0 e recall 0.) → leitor
  precisa varrer com `raw_decode`.
- **O GPT tem aspas não-escapadas** em frases com discurso citado
  (`declarou: "..."`), que quebram o JSON. Recuperamos a maioria; **uma pequena
  fração é irrecuperável** por regex (aspas de fala seguidas de vírgula/ponto do
  texto). Impacto pequeno, não muda ranking.
- **DptOIE re-tokeniza e descontrai as frases** (expande contrações, mexe em
  espaços/pontuação). Sem **alinhar ao gold** primeiro, o pareamento por frase
  falha e o modelo pontua **zero** injustamente.

---

## 11. Validação: DptOIE-Java **é igual** ao port DptOIE-PY?

**Não são iguais** — mas a diferença **não é do algoritmo**, e sim de
**configuração**:

- O **DptOIE-Java** roda em modo que **super-gera** (várias variantes de arg2 por
  relação) → a precisão colapsa e ele pontua bem abaixo do port.
- O jar ainda tem um **defeito de descontração** (escreve "en o" em vez de
  "em o"/"no"), o que atrapalha o casamento de tokens.
- Filtrando por **coerência/minimalidade** (colunas que o DptOIE fornece), o gap
  provavelmente encolhe — é o teste que fecha a validação.
- Conclusão pro artigo: *"o port Python e o jar Java divergem principalmente por
  super-geração/configuração, não pelo método."*
- **Confirmado depois com um segundo arquivo DptOIE** que o usuário coletou de
  novo: mesma assinatura (F1=0,296 no BIA, razão de triplas 3,93× o gold,
  triplas aninhadas por relação). Ou seja, não foi acaso de uma coleta ruim —
  é o comportamento padrão dessa versão do extrator.
- Comparação dos **três** extratores da FORMAS lado a lado (Flair, Py, Java),
  com os números: **ver §15**.

---

## 12. Bugs de pipeline encontrados e corrigidos

- **Scorer CaRB:** havia uma troca de variável (`prec_num`↔`rec_num`) que zerava a
  precisão e, com isso, o **F1 de TODOS os modelos no OIEC**. Corrigido — os
  números passaram a fazer sentido.
- **Matcher por campo** pareia por **frase exata** (por isso o DptOIE-Java dava
  zero antes do alinhamento); o **CaRB** pareia por **similaridade (fuzzy)**, mais
  tolerante. Bom saber ao comparar as duas tabelas.

---

## 13. Pendências de maior retorno

1. **k rodadas + consenso** — o guardrail que ataca de fato a estocasticidade das
   LLMs (o bootstrap não cobre isso).
2. **Teste de contaminação** — barato e blinda contra "o modelo já viu o corpus?".
3. **Filtrar DptOIE-Java por coerência** — fecha a validação Java vs. PY.
4. (Opcional) **Unified** — coletar as LLMs no corpus unificado (362 frases) para
   testar generalização com mais dados.

---

## 14. Por que o OIEC-PT dá métricas piores — evidência quantificada

Quatro fatores, cada um com um número que o sustenta (fontes: `Outputs/metricas/`,
heatmaps de Triplas/Consenso/Cobertura, forest plot do bootstrap):

**(a) Corpus 2,6× menor → mais ruído estatístico.**
BIA tem 262 frases, OIEC-PT tem 100. O IC do PTOIE-Flair tem largura 0,081 no
BIA (0,618–0,699) contra 0,148 no OIEC-PT (0,518–0,666) — quase o dobro de
incerteza só pelo tamanho da amostra, sem precisar invocar "qualidade pior".

**(b) A regra de factualidade (S1) pune os modelos por um critério que eles
não conhecem.** O gold do OIEC-PT só aceita fatos claramente afirmados;
sub-orações que parecem extraíveis (ex.: dentro de fala reportada,
`declarou: "..."`) são legitimamente excluídas do gold, mas os modelos
extraem do mesmo jeito. Isso produz **falso positivo sistemático e
compartilhado**: no prompt OIEC, o % de erro em comum entre LLMs é
**74–89% no OIEC-PT contra 52–59% no BIA** — no OIEC-PT os modelos erram
*juntos*, na mesma armadilha, muito mais que no BIA. É a marca de uma
convenção de anotação que os modelos desconhecem, não de "frase mais
confusa".

> **Exemplo real** (`consenso_forte_Respostas_ExtrativoOIEC-PT.csv`) — frase:
> *"O seu representante de políticas da natureza, Jeff Knott, declarou:
> 'Eu ficaria espantado se uma proibição ou um licenciamento fosse com base
> nestes fundamentos'."*
> Claude, Gemini e Grok — os três — extraíram
> `(O seu representante..., Jeff Knott | declarou | Eu ficaria espantado...)`,
> tratando **a fala citada inteira como arg2**. Faz sentido à primeira vista
> ("declarou algo" → o algo é o arg2), mas o conteúdo da fala é uma
> **opinião hipotética de terceiros** ("eu ficaria espantado **se**..."), não
> um fato afirmável pela regra S1 — por isso não está no gold. O mesmo padrão
> se repete em pelo menos mais duas frases do corpus com `disse`/`acrescentou`
> (linhas 165–167 e 196–198 do mesmo CSV). Três modelos diferentes, o mesmo
> "erro" — porque não é erro de leitura, é uma convenção de anotação que
> nenhum deles conhece.

**(c) Sintaxe mais complexa (oração encaixada, discurso reportado).**
Aparece direto nos lotes: o tercil mais difícil do OIEC-PT tem gap
Flair−LLMs de **0,235**, contra **0,077–0,082** nos demais tercis (do OIEC-PT
e do BIA) — o "pior caso" do OIEC-PT é proporcionalmente muito mais punitivo
que o do BIA.

> **Exemplo real** — frase do OIEC-PT: *"O seu pescoço avança em confronto com
> veias acentuadas, as suas mãos tremem."* — duas orações **justapostas por
> vírgula** (sem conjunção), estilo comum em prosa literária/jornalística
> informal, raro no registro enciclopédico do BIA. O DptOIE tratou a segunda
> oração como se fosse continuação do arg2 da primeira, gerando variantes
> como `(O seu pescoço | avança | em confronto com veias acentuadas, as suas
> mãos tremem)` — uma tripla que mistura dois fatos diferentes por causa da
> pontuação. É o tipo de estrutura que puxa o tercil difícil do OIEC-PT para
> baixo.

**(d) Cobertura mais baixa — os modelos "desistem" mais.**
No prompt PTOIE, Grok cai de 99,2% (BIA) para 95% (OIEC-PT), Gemini de 100%
para 91%; no prompt OIEC, Gemini cai a 80% e Grok a 78% (contra quase-100%
no BIA). Frase sem tentativa nenhuma é recall perdido de graça, antes mesmo
de discutir qualidade da extração.

**Conclusão:** o OIEC-PT não é "pior" por acaso — é menor (mais ruído), tem
uma regra de anotação que gera erro sistemático compartilhado, tem sintaxe
mais difícil no seu pior tercil, e os modelos cobrem menos frases nele.

---

## 15. Por que os três extratores da FORMAS (Flair, Py, Java) não performam igual

Ranking consistente nos dois corpora: **PTOIE-Flair > DptOIE-Py > DptOIE-Java.**
A explicação não é "quem entende melhor o português" — é **quantas triplas
cada um decide emitir por relação**.

> **Exemplo real — a MESMA frase do BIA nos três extratores**, frase 1 do
> gold: *"A universidade é afiliada a a Congregação de a Santa Cruz (em latim
> Congregatio a Sancta Cruce, pós-nominais abreviados"*. Gold:
> `(A universidade | é | afiliada a a Congregação de a Santa Cruz)` e
> `(A universidade | é afiliada a | a Congregação de a Santa Cruz)`.
> - **PTOIE-Flair** devolveu **1 tripla**: `(A universidade | é afiliada a |
>   a Congregação de a Santa Cruz)` — bate **exatamente** com a 2ª tripla do
>   gold. Nada a mais, nada a menos.
> - **DptOIE-Py** devolveu **1 tripla**, mas com o arg2 estourado:
>   `(A universidade | é afiliada | a a Congregação de a Santa Cruz ( em
>   latim Congregatio a Sancta Cruce , pós-nominais abreviados)` — pegou a
>   relação certa, mas grudou o parêntese inteiro no argumento.
> - **DptOIE-Java** devolveu **8 triplas** pra essa mesma relação, entre elas:
>   `(...| é afiliada | a a Congregação de a Santa Cruz)`,
>   `(...| é afiliada | a a Congregação... ( em latim Congregatio a Sancta
>   Cruce)`, `(...| é afiliada | ( em latim Congregatio a Sancta Cruce)`,
>   `(...| é afiliada | ( em latim Congregatio , pós - nominais)`,
>   `(...| é afiliada | ( em latim Congregatio abreviados)` — recortes
>   diferentes do **mesmo parêntese**, cada um virando uma tripla própria.
>   Isso, multiplicado por 262 frases, é o que produz a razão 3,93×.
>
> Os três "leram" a frase da mesma forma (identificaram sujeito, verbo,
> parêntese); a diferença inteira está em **quantas variantes decidir
> emitir** — 1, 1 (bagunçada) ou 8.

**PTOIE-Flair (neural) — conservador e limpo.**
Razão de triplas preditas/gold: **0,541× (BIA) / 0,640× (OIEC-PT)** — extrai
*menos* que o gold, não mais. Precisão altíssima (0,756 BIA / 0,609 OIEC-PT).
O custo: cobertura de só 80–81% — não tenta ~1 em cada 5 frases (provável
falta de confiança na detecção do verbo). Erra por **omissão**, não por
ruído: sendo neural, aprende a produzir uma decisão holística única por
predicado, sem decompor a frase em variações.

**DptOIE-Py — no meio, porque filtra melhor.**
Razão de triplas: **0,888× (BIA) / 0,949× (OIEC-PT)** — perto de 1×, nem
super-gera nem sub-gera. É a mesma extração baseada em regras do Java, mas
com um filtro que descarta variantes redundantes antes de emitir a saída —
e é exatamente esse filtro que explica o F1 bem mais alto (0,569 vs. 0,296
no BIA; 0,487 vs. 0,418 no OIEC-PT).

**DptOIE-Java (regras, sem filtro) — o pior, por super-geração severa.**
Razão de triplas: **3,93× no BIA** (o maior super-gerador do estudo inteiro,
em qualquer prompt) e **2,04× no OIEC-PT**. Para uma única relação, ele emite
a "casca" mais todas as sub-extrações aninhadas como triplas separadas — uma
frase chegou a gerar 7–8 variantes de arg2, cada uma um recorte diferente da
mesma informação. O CaRB pune isso com força na precisão (cada tripla a mais
entra no denominador), por isso o F1 despenca mesmo o recall sendo razoável
(0,80 BIA / 0,74 OIEC-PT — ele *acha* os fatos, só que enterrados em ruído).

**Achado extra (padrão observado, não causal):** a super-geração do Java é
*maior* no BIA (3,93×) que no OIEC-PT (2,04×) — possivelmente porque frases
de Wikipédia têm mais oração-aposto entre parênteses, dando mais gatilhos
para a lógica de fragmentação em cascata do que o texto do OIEC-PT.

**A lição que amarra com o achado central (§1):** a diferença entre o melhor
e o pior extrator especializado da FORMAS não é sobre entender melhor ou
pior o português — é sobre **saber quando parar de extrair**. É a mesma
lógica que separa especializados de LLMs no estudo inteiro.

---

## Resumo em uma frase

**O especializado neural vence as LLMs por ser preciso enquanto elas super-geram;
essa vantagem é estatisticamente significativa (teste pareado, p&lt;0,05) tanto no
BIA quanto no OIEC-PT, ainda que mais apertada no OIEC-PT — corpus menor,
regra de anotação mais rígida e sintaxe mais difícil tornam esse corpus
naturalmente mais ruidoso, o que reforça (não invalida) a necessidade dos
guardrails (mais dados, k rodadas, controle de contaminação).**
