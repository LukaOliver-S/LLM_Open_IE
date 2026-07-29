# Rules:

## DPTOIE:
Regras estruturais do DptOIE (extraídas do artigo):

**Constituintes da tripla ⟨ARG1, REL, ARG2⟩**

ARG1 (sujeito): parte de nsubj/nsubj:pass. Inclui os dependentes: Modificadores (nummod, advmod, nmod, amod) e Outros (dep, obj, conj, appos — este último quando rotulado pelo POS tagger como "NUM").

REL (relação): parte do nó pai do sujeito, ou de nós filhos rotulados como acl:part. Tokens antes do nó pai do sujeito: verbos auxiliares/copulativos (aux, aux:pass, cop), Objetos (obj, iobj), modificador adverbial (advmod), Outros (expl:pv, mark). Tokens depois do nó pai do sujeito: Outros (expl:pv, acl:part).

ARG2: parte da raiz da relação. Inclui Objetos (obj, iobj), Modificadores (nmod, nummod, advmod, amod), Complemento (xcomp), modificador de oração complemento/adverbial (ccomp e advcl, desde que não tenham nós filhos rotulados como nsubj/nsubj:pass), Outros (acl:relcl, conj, appos, acl:part, dep).

A preposição permanece no ARG2.

**Extração via DFS**

A extração requer sentença com Sujeito (ARG1), frase verbal (REL) e um ou mais argumentos dependentes da relação (ARG2). Um DFS busca primeiro os sujeitos; depois a relação, por um DFS a partir do nó pai do sujeito ou de nó filho rotulado como acl:part; por fim o ARG2, por um DFS a partir dos nós filhos da relação. Extrações de eventos ocorrem quando o DFS encontra um nó folha. ARG2 pode ser combinado a partir de dois ARG2 distintos para gerar um fato com mais informação.

**R1 — Conjunções coordenadas (CC)**

Aplicadas apenas às conjunções "e" e "ou", a partir de relações de dependência rotuladas como conj. Coordenação de verbos: verifica se o nó filho do nó pai do sujeito está rotulado como conjunção e é verbo; se válido, gera outra tripla com o verbo coordenado. Coordenação de argumentos (enumeração): gera uma tripla para cada elemento coordenado.

**R2 — Orações subordinadas**

Adjetiva (relativa): quando o pronome relativo é rotulado como sujeito (nsubj) e seu nó pai é rotulado como acl:relcl, o pronome relativo é substituído pelo antecedente; o DFS parte do nó pai do antecedente para encontrar o argumento que substitui o pronome relativo.

Substantiva: liga a tripla da oração principal à tripla da oração subordinada por meio da relação de dependência ccomp entre os verbos das duas orações; a conjunção "que" é adicionada como ARG2 da oração principal, gerando um fato composto por duas triplas encadeadas. Requer que ambas as orações tenham sujeitos explícitos.

Adverbial: mesmo tratamento da substantiva, com a conexão feita por advcl em vez de ccomp.

**R3 — Apositivos**

Apositivo rotulado como nome próprio (PNOUN): cria uma cláusula sintética com o verbo "é", gerando uma tripla entre o termo e o apositivo.

**R4 — Transitividade**

O apositivo é considerado equivalente ao termo que ele qualifica; a partir dessa equivalência, geram-se triplas adicionais substituindo o termo pelo apositivo (e vice-versa) nas demais triplas.


---

## OIEC-PT:

#### Regras estruturais do OIEC-PT (E1–E9):

**E1 — Estrutura fundamental da relação:** Uma relação válida é formada por ⟨ARG1, REL, ARG2⟩, onde REL contém o verbo principal e há dependência sintática clara entre o verbo e seus argumentos; geralmente ARG1 corresponde ao sujeito e ARG2 ao complemento.

**E2 — Concordância:** ARGs e REL devem preservar concordância de número/gênero/pessoa com a sentença.

**E3 — Delimitação dos argumentos:** Cada ARG deve incluir o núcleo nominal e modificadores/determinantes essenciais (artigos, adjetivos restritivos, numerais, pronomes, adjuntos nominais). Adjuntos não-essenciais (como oração relativa não-restritiva) devem ser evitados.

**E4 — Preposição em REL:** Se o verbo rege uma preposição, ela deve ser incluída em REL.

**E4.1 — Contração preposição + artigo:** Contrações de preposição e artigo devem ser decompostas, com a preposição permanecendo em REL e o artigo colocado no início de ARG2.

**E4.2 — Locuções prepositivas:** Expressões lexicalizadas (ex.: ao longo de) não devem ser fragmentadas.

**E5 — Natureza dos argumentos:** Ao menos um ARG é um SN cujo núcleo é um substantivo ou pronome (referente nominal claro).

**E6 — Relações n-árias:** Relações n-árias, quando o sentido pode ser preservado, devem ser decompostas (reificadas) em relações binárias.

**E7 — Coordenação aditiva:** Gerar múltiplos fatos para cada elemento coordenado (preferido), ou um único fato com a coordenação.

**E8 — Argumentos oracionais:** ARG2 (ou ARG1) pode ser uma oração inteira; a factualidade da oração subordinada é avaliada separadamente (ver S1).

**E9 — Expressões multipalavra:** Tratar expressões multipalavra (prepositivas/adverbiais/conjuntivas) como unidades: se fazem parte da relação, entram inteiras em REL; se modificam o ARG, permanecem no argumento (E3).


#### Regras semânticas do OIEC-PT (S1–S5):

**S1 — Factualidade e implicação:** Apenas proposições afirmadas ou acarretadas (entailed) pela sentença devem ser extraídas. Deve-se ter cuidado com modais, relatos de crença/fala, condicionais e negação.

**S2 — Mínimo vs. extenso:** Escolher entre um argumento mínimo ou mais extenso dependendo da identificabilidade contextual (seguindo E3).

**S3 — Evitar complexidade/aninhamento:** Não embutir uma relação separável dentro de um ARG; preferir a decomposição (ver E6).

**S4 — Análise linguística consistente:** A extração deve apoiar-se numa interpretação sintático-semântica defensável; em casos de ambiguidade, selecionar a leitura mais plausível.

**S5 — Sem inferência externa:** Não validar fatos que dependam de conhecimento externo ou inferência lógica não-declarada (ex.: transitividade).


## Abstractive OpenIE for Portuguese (Cabral et al.):

**T1 — Desmembramento de coordenação (coordination dismemberment):** Argumentos ou predicados coordenados são decompostos em triplas atômicas separadas. Aplica-se a coordenação de sujeito, de objeto e de predicado. O verbo é flexionado do plural para o singular para manter a correção gramatical em cada tripla atômica ("Breno Silveira e Andrucha Waddington dirigiram o filme" → ⟨Breno Silveira, dirigiu, o filme⟩; ⟨Andrucha Waddington, dirigiu, o filme⟩).

**T2 — Normalização de apostos (appositive normalization):** Apostos introduzem relações de identidade ou nomeação. O nome canônico da entidade fica disponível para centralização do sujeito (subject centering) nas triplas subsequentes ("O novo longa-metragem, Vitória, estreia hoje" → ⟨O novo longa-metragem, chama-se, Vitória⟩; ⟨Vitória, estreia, hoje⟩).

**T3 — Resolução de correferência (coreference resolution):** Quando não-ambíguo pelo contexto da sentença, descrições definidas ou pronomes são resolvidos aos seus antecedentes para produzir triplas canonicalizadas ("O Globoplay é uma plataforma de streaming. A plataforma marcou o lançamento" → ⟨Globoplay, é, uma plataforma de streaming⟩; ⟨Globoplay, marcou, o lançamento⟩).

**T4 — Canonicalização de relação (relation canonicalization):** Construções verbais complexas, voz passiva e expressões perifrásticas são normalizadas em predicados canônicos mais simples, preservando o sentido ("O filme é estrelado por Fernanda Montenegro" → ⟨O filme, tem como estrela, Fernanda Montenegro⟩ ou ⟨Fernanda Montenegro, estrela, o filme⟩).
Além das transformações, os dois princípios centrais que as regem:
Fidelidade (faithfulness): Toda tripla gerada deve ser acarretada (entailed) pela sentença-fonte; o sistema não pode alucinar fatos ausentes do input.
Atomicidade (atomicity): Cada tripla deve expressar exatamente um fato relacional; estruturas complexas devem ser decompostas em triplas atômicas independentes.

#### Regras Estruturais (E)

**E1. Estrutura Fundamental da Relação**
Uma relação válida é representada por uma tripla *(ARG1, REL, ARG2)*. ARG1 corresponde, em geral, ao sujeito; REL contém o verbo principal (ou núcleo verbal); ARG2 corresponde ao complemento principal da relação, podendo ser um sintagma nominal, uma oração subordinada substantiva ou um adjunto essencial.

**E1.1. Dependência Sintática**
A relação extraída deve refletir uma dependência sintática direta entre ARG1, REL e ARG2. Não devem ser criadas triplas que conectem elementos sem ligação sintática clara na sentença.


**E2. Concordância**
Os elementos extraídos devem preservar a concordância de número, gênero e pessoa presente na sentença original.


**E3. Delimitação dos Argumentos (Sintagmas Nominais)**
Os argumentos devem corresponder ao sintagma nominal completo, incluindo núcleo nominal e modificadores essenciais, como artigos, adjetivos restritivos, numerais, pronomes, possessivos e complementos nominais necessários para identificar corretamente a entidade.


**E4. Preposições e REL**
Quando o verbo rege uma preposição para introduzir um argumento, essa preposição deve ser incorporada à relação (REL), e não ao argumento.


**E4.1. Contração de Preposição + Artigo**
Quando houver contração entre preposição regida pelo verbo e artigo (*do, da, no, na, pelo, à* etc.), a preposição permanece em REL e o artigo inicia ARG2. Essa regra não se aplica a contrações internas a um sintagma nominal.


**E5. Natureza Nominal dos Argumentos**
Pelo menos um dos argumentos deve possuir núcleo nominal (substantivo ou pronome). Idealmente ambos os argumentos são sintagmas nominais ou um sintagma nominal e uma oração substantiva.


**E6. Desmembramento de Relações N-árias**
Sempre que possível, relações envolvendo múltiplos argumentos devem ser divididas em várias triplas binárias, preservando o significado da sentença.


**E7. Conjunções Coordenativas Aditivas**
Quando coordenações aditivas unem múltiplos elementos com a mesma função sintática, deve-se priorizar a geração de uma tripla para cada elemento coordenado.


**E8. Argumentos Clausais**
Os argumentos podem ser constituídos por orações inteiras, especialmente orações subordinadas substantivas que funcionem como complemento da relação.


**E9. Locuções e Expressões Multipalavra**
Locuções prepositivas, adverbiais ou conjuntivas devem ser tratadas como unidades sintático-semânticas. Quando fizerem parte da relação verbal, devem ser incorporadas integralmente em REL.


**E10. Relações Implícitas em Apostos**
Construções em aposto podem originar relações implícitas. O termo principal torna-se ARG1, o aposto torna-se ARG2 e a relação é representada por um verbo de ligação implícito (preferencialmente "ser") ou por uma forma equivalente semanticamente adequada.


#### Regras Semânticas (S)

**S1. Factualidade e Implicação**
Devem ser extraídas apenas relações afirmadas como fatos pelo texto. Relações presentes em contextos de modalidade, hipótese, condição, crença, opinião ou possibilidade não devem ser extraídas como fatos, exceto quando a própria modalidade constitui a relação.


**S2. Relevância Semântica e Delimitação Precisa do Argumento**
Os argumentos devem representar exatamente os participantes centrais da relação, correspondendo ao sintagma nominal completo e evitando tanto truncamentos quanto expansões desnecessárias.


**S3. Evitar Argumentos Excessivamente Complexos / Relações Aninhadas**
Os argumentos devem ser semanticamente coesos. Relações distintas presentes dentro de um argumento devem, sempre que possível, ser extraídas como triplas independentes.



**S4. Análise Linguística Consistente**
A extração deve basear-se em uma análise sintática e semântica consistente da sentença. Em casos ambíguos, deve-se escolher a interpretação linguisticamente mais provável.


**S5. Inferências Limitadas e Textualmente Ancoradas**
As relações devem ser fundamentadas no texto. São permitidas apenas inferências diretamente suportadas pela própria sentença ou contexto imediato, como resolução de correferência, relações de aposto e enriquecimentos mínimos. Inferências baseadas em conhecimento externo ou deduções complexas não devem ser realizadas.


**S6. Resolução de Co-referência Intra-textual para Sentido Completo**
Sempre que um argumento for um pronome ou expressão anafórica com antecedente claro e inequívoco no texto, ele deve ser substituído pelo sintagma nominal antecedente, tornando a tripla autocontida.



**S7. Simplificação de Argumentos para Generalização**
É permitida a simplificação controlada de argumentos quando isso preserva a factualidade da relação e produz uma representação mais geral e concisa.



**S8. Enriquecimento Contextual de Argumentos**
Após a resolução de co-referência, os argumentos podem ser reescritos para incorporar explicitamente o contexto necessário ao entendimento da tripla, desde que toda a informação adicionada seja diretamente derivada do próprio texto.

---
## Regras do PTOIE-Dep

## Regras Estruturais

### E1. Estrutura Fundamental da Tripla

Cada tripla é composta por sujeito (ARG1), relação (REL) e complemento (ARG2), extraídos a partir da árvore de dependências. Todo verbo da sentença é considerado núcleo potencial de uma relação. Uma tripla só é válida quando possui os três elementos; se não houver complemento (ARG2), a tripla não deve ser gerada.

### E2. Identificação do Sujeito (ARG1)

O núcleo do sujeito corresponde às dependências `nsubj`, `nsubj:pass` (passivo) ou `csubj` (oracional). Ao núcleo somam-se, como expansão, os dependentes `det`, `case`, `amod`, `nmod`, `nummod`, `conj` e `appos`. Quando um pronome relativo (como "que") atua como sujeito de uma oração adjetiva, ele é resolvido diretamente ao seu antecedente (head), que passa a ocupar o ARG1 — sem parênteses ou anotações.

### E3. Sujeito de Existenciais e Voz Passiva

Em construções de voz passiva (`aux:pass`) e com verbos existenciais como "haver" e "existir", o sujeito lógico é localizado na posição de objeto. Exemplo: de "Há muitas pessoas na festa", extrai-se ⟨muitas pessoas, há, na festa⟩.

### E4. Construção da Relação (REL)

A relação é expandida a partir do verbo principal, incorporando verbos auxiliares e copulativos (`aux`, `aux:pass`, `cop`), modificadores adverbiais que alteram o sentido da ação — em especial advérbios de negação ("não", "jamais") — e clíticos (`expl:pv`). Isso preserva nuances de polaridade e modalidade, distinguindo ⟨ele, gosta, de pizza⟩ de ⟨ele, não gosta, de pizza⟩.

### E5. Construção do Complemento (ARG2)

O núcleo do complemento corresponde a `obj`, `iobj`, `obl`, `xcomp` ou `ccomp`. À sua expansão somam-se os dependentes `det`, `case`, `amod`, `nmod`, `nummod`, `conj`, `appos`, `advcl` e `acl`. O complemento deve ser o mais completo possível sem embutir outra relação separável.

### E6. Preposições

As preposições regidas pelo verbo permanecem incorporadas ao ARG2, não sendo deslocadas para REL. Locuções prepositivas lexicalizadas não devem ser fragmentadas.

## Regras de Fenômenos Complexos

### E7. Conjunções Coordenativas (CC)

Coordenações introduzidas por "e" ou "ou" geram triplas independentes. Duas operações são aplicadas:

* **Propagação de preposição:** em estruturas coordenadas, a preposição regida é propagada para cada elemento coordenado, garantindo correção gramatical (ex.: "gosto de maçãs e peras" gera um complemento preposicionado para cada fruta).
* **Distribuição de complemento compartilhado:** quando verbos coordenados compartilham um mesmo complemento, ele é distribuído para cada verbo (ex.: "O governo comprou, limpou e vendeu a propriedade" gera uma tripla por verbo, todas com o mesmo complemento).

### E8. Orações Subordinadas (SC)

Ao encontrar uma oração subordinada (`advcl`, `ccomp`), verifica-se se ela possui sujeito explícito. Se possui, realiza-se uma extração recursiva a partir do verbo subordinado, gerando uma tripla própria para a subordinada além da tripla da principal (ex.: "O diretor afirmou que a empresa cresceu" gera ⟨O diretor, afirmou, que a empresa cresceu⟩ e a tripla da subordinada). Se não possui sujeito explícito, a oração é tratada como complemento verbal da principal, permanecendo no ARG2.

### E9. Apostos

Um aposto (`appos`) produz uma relação sintética com o verbo "é", capturando fatos de identidade ou tipificação. Exemplo: de "Lula, o ex-presidente, ...", extrai-se ⟨Lula, é, o ex-presidente⟩.

### E10. Inferência por Transitividade

A partir das relações já extraídas de um aposto, novas triplas são inferidas por transitividade: se o método extrai ⟨A, é, B⟩ e ⟨A, R, C⟩, então deduz ⟨B, R, C⟩. Exemplo: de "Lula, o ex-presidente, viajou para a Europa", além das triplas diretas, gera-se ⟨o ex-presidente, viajou, para a Europa⟩.

## Sanitização

### E11. Sanitização

Cada elemento da tripla é limpo ao final: removem-se pontuações e conectores soltos, e descartam-se extrações sem verbo na relação.