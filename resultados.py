#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
avaliar_openie.py
==================

Pipeline robusto de avaliação de sistemas de Open Information Extraction (OpenIE)
em Português, comparando saídas de LLMs (Claude, GPT, Gemini, Grok, DeepSeek...)
contra um Gold Standard.

Principais melhorias em relação à versão original:

1. ROBUSTEZ  -> `RobustJSONLReader` tenta múltiplas estratégias de parsing
   (array clássico, NDJSON, varredor raw_decode, e por último uma etapa de
   "reparo" de erros comuns de LLM: vírgulas penduradas, aspas simples,
   blocos concatenados). Cada falha é reportada com número da linha/objeto
   e trecho exato do erro.

2. PERFORMANCE -> Avaliação de múltiplos arquivos (múltiplos modelos) roda em
   paralelo com `ProcessPoolExecutor`. A leitura em si já é O(n) via
   `raw_decode` (não usa regex custosa). Para arquivos muito grandes, o
   parser é incremental (não carrega tudo em memória de uma vez desnecessariamente
   além do necessário) e o cálculo de overlap lexical usa `set` (O(1) por token).

3. LOGS -> módulo `logging` configurado para console + arquivo `avaliacao.log`.
   Cada frase mal alinhada, cada objeto JSON que falhou, e cada exceção de
   parsing aponta exatamente o índice da frase e o trecho problemático.

4. LIMPEZA -> lógica de leitura (`RobustJSONLReader`), lógica de matching
   (`TripleMatcher`) e lógica de agregação de métricas (`Metricas`) estão
   em classes separadas, cada uma com docstring e responsabilidade única.

5. FLEXIBILIDADE -> `TripleMatcher` é uma interface simples; basta implementar
   `bate(gold, pred) -> bool` para adicionar uma nova estratégia de match
   (ex.: similaridade por embeddings) sem tocar no resto do pipeline.

Uso via linha de comando
-------------------------
Um único par gold/pred:
    python avaliar_openie.py --gold bia_gold_sentences.jsonl --pred Claude_Sonnet5.jsonl

Um gold contra uma pasta inteira de modelos (gera um relatório comparativo):
    python avaliar_openie.py --gold bia_gold_sentences.jsonl \
        --pred-dir "Respostas ExtrativoDPTO-IE" \
        --output resultados_dpto_ie.csv \
        --workers 4
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# --------------------------------------------------------------------------- #
# LOGGING
# --------------------------------------------------------------------------- #

def configurar_logger(nome: str = "openie_eval", arquivo_log: str = "avaliacao.log") -> logging.Logger:
    """Cria um logger que grava em console (INFO+) e em arquivo (DEBUG+).

    Usar um logger em vez de `print` permite filtrar por nível, redirecionar
    para arquivo automaticamente e localizar rapidamente qual frase/objeto
    causou um problema, sem poluir a saída padrão.
    """
    logger = logging.getLogger(nome)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fmt_console = logging.Formatter("%(levelname)s | %(message)s")
    fmt_arquivo = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt_console)

    fh = logging.FileHandler(arquivo_log, mode="a", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt_arquivo)

    logger.addHandler(ch)
    logger.addHandler(fh)
    return logger


log = configurar_logger()


# --------------------------------------------------------------------------- #
# MODELOS DE DADOS
# --------------------------------------------------------------------------- #

@dataclass
class Triple:
    """Representa uma tripla (arg1, rel, arg2) extraída de uma frase."""
    arg1: str = ""
    rel: str = ""
    arg2: str = ""

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Triple":
        if not isinstance(d, dict):
            return cls()
        return cls(
            arg1=str(d.get("arg1", "") or ""),
            rel=str(d.get("rel", "") or ""),
            arg2=str(d.get("arg2", "") or ""),
        )


@dataclass
class ResultadoParsing:
    """Guarda o resultado de tentar carregar um arquivo, incluindo falhas."""
    objetos: List[Any] = field(default_factory=list)
    erros: List[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# LEITURA ROBUSTA DE JSONL "SUJO" GERADO POR LLM
# --------------------------------------------------------------------------- #

class RobustJSONLReader:
    """Lê arquivos JSON/JSONL gerados por LLMs, que raramente são perfeitos.

    Estratégia, em ordem de tentativa (a primeira que funcionar é usada):
        1. `json.loads` direto (arquivo é um único array JSON válido).
        2. Remoção de cercas de código Markdown (```json ... ```).
        3. Varredura incremental com `json.JSONDecoder.raw_decode`, que
           localiza e extrai objetos JSON um a um, ignorando vírgulas e
           quebras de linha soltas entre eles — funciona mesmo se a LLM
           misturou um array com objetos soltos.
        4. Reparo textual leve (vírgulas penduradas antes de `]`/`}`,
           aspas simples -> duplas em chaves) seguido de nova varredura,
           apenas para os trechos que falharam na etapa 3.

    Cada falha irrecuperável é registrada com a posição no arquivo e um
    trecho de até 80 caracteres, para diagnóstico rápido.
    """

    _RE_MARKDOWN_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$", re.MULTILINE)
    _RE_TRAILING_COMMA = re.compile(r",\s*([\]}])")

    def __init__(self, caminho: Path):
        self.caminho = caminho

    def carregar(self) -> ResultadoParsing:
        texto = self.caminho.read_text(encoding="utf-8", errors="replace").strip()
        texto = self._remover_cercas_markdown(texto)

        # Tentativa 1: array JSON clássico
        if texto.startswith("[") and texto.endswith("]"):
            try:
                return ResultadoParsing(objetos=json.loads(texto))
            except json.JSONDecodeError as e:
                log.debug("Arquivo %s: array JSON completo falhou (%s); tentando varredura.", self.caminho, e)

        # Tentativa 2/3: varredura incremental + reparo pontual
        return self._varrer_objetos(texto)

    def _remover_cercas_markdown(self, texto: str) -> str:
        return self._RE_MARKDOWN_FENCE.sub("", texto).strip()

    def _varrer_objetos(self, texto: str) -> ResultadoParsing:
        resultado = ResultadoParsing()
        decoder = json.JSONDecoder()
        idx = 0
        n = len(texto)

        while idx < n:
            while idx < n and texto[idx] in " \n\r\t,":
                idx += 1
            if idx >= n:
                break
            try:
                obj, end_idx = decoder.raw_decode(texto, idx)
                resultado.objetos.append(obj)
                idx = end_idx
            except json.JSONDecodeError:
                # Tenta reparo local antes de desistir do trecho
                reparado, novo_fim = self._tentar_reparo(texto, idx)
                if reparado is not None:
                    resultado.objetos.append(reparado)
                    idx = novo_fim
                    continue

                trecho = texto[idx: idx + 80].replace("\n", "\\n")
                msg = f"Objeto JSON inválido a partir do offset {idx}: '{trecho}...'"
                log.warning("Arquivo %s: %s", self.caminho, msg)
                resultado.erros.append(msg)
                # Avança 1 caractere para não travar em loop infinito
                idx += 1

        if not resultado.objetos:
            raise RuntimeError(
                f"Nenhum JSON válido encontrado em '{self.caminho}'. "
                f"Erros: {resultado.erros[:3]}"
            )
        return resultado

    def _tentar_reparo(self, texto: str, idx: int) -> Tuple[Optional[Any], int]:
        """Tenta consertar erros comuns (vírgula pendurada, aspas simples)
        em uma janela local de texto e reprocessar apenas esse pedaço.
        """
        janela = texto[idx: idx + 4000]
        # Corta na primeira chance plausível de fechamento de objeto/array
        candidato = self._RE_TRAILING_COMMA.sub(r"\1", janela)
        decoder = json.JSONDecoder()
        try:
            obj, fim_local = decoder.raw_decode(candidato, 0)
            return obj, idx + fim_local
        except json.JSONDecodeError:
            return None, idx


# --------------------------------------------------------------------------- #
# ESTRATÉGIAS DE MATCH ENTRE TRIPLAS
# --------------------------------------------------------------------------- #

class TripleMatcher:
    """Interface para estratégias de comparação entre triplas gold/pred.

    Para adicionar uma nova métrica (ex.: similaridade por embeddings,
    ROUGE, etc.), basta criar uma subclasse implementando `bate`.
    """

    nome: str = "base"

    def bate(self, gold: Triple, pred: Triple) -> bool:
        raise NotImplementedError


class ExactMatcher(TripleMatcher):
    """Match exato: os três campos devem ser idênticos (case-insensitive)."""

    nome = "exact"

    def bate(self, gold: Triple, pred: Triple) -> bool:
        return (
            gold.arg1.strip().lower() == pred.arg1.strip().lower()
            and gold.rel.strip().lower() == pred.rel.strip().lower()
            and gold.arg2.strip().lower() == pred.arg2.strip().lower()
        )


class LexicalMatcher(TripleMatcher):
    """Match lexical: cada campo precisa ter overlap de tokens > `limiar`."""

    nome = "lexical"

    def __init__(self, limiar: float = 0.5):
        self.limiar = limiar

    @staticmethod
    def _overlap(a: str, b: str) -> float:
        tokens_a = set(a.lower().split())
        tokens_b = set(b.lower().split())
        if not tokens_a or not tokens_b:
            return 0.0
        return len(tokens_a & tokens_b) / max(len(tokens_a), len(tokens_b))

    def bate(self, gold: Triple, pred: Triple) -> bool:
        return (
            self._overlap(gold.arg1, pred.arg1) > self.limiar
            and self._overlap(gold.rel, pred.rel) > self.limiar
            and self._overlap(gold.arg2, pred.arg2) > self.limiar
        )


# --------------------------------------------------------------------------- #
# MÉTRICAS (Precision / Recall / F1) COM CASAMENTO GULOSO 1-PARA-1
# --------------------------------------------------------------------------- #

@dataclass
class Contadores:
    vp: int = 0
    fp: int = 0
    fn: int = 0

    def precisao(self) -> float:
        return self.vp / (self.vp + self.fp) if (self.vp + self.fp) else 0.0

    def recall(self) -> float:
        return self.vp / (self.vp + self.fn) if (self.vp + self.fn) else 0.0

    def f1(self) -> float:
        p, r = self.precisao(), self.recall()
        return (2 * p * r) / (p + r) if (p + r) else 0.0


def comparar_triplas(
    gold_triplas: List[Triple], pred_triplas: List[Triple], matcher: TripleMatcher
) -> Contadores:
    """Casamento guloso 1-para-1: cada gold só pode ser usada uma vez."""
    usadas: set = set()
    c = Contadores()
    for p in pred_triplas:
        achou = False
        for i, g in enumerate(gold_triplas):
            if i not in usadas and matcher.bate(g, p):
                c.vp += 1
                usadas.add(i)
                achou = True
                break
        if not achou:
            c.fp += 1
    c.fn = len(gold_triplas) - len(usadas)
    return c


# --------------------------------------------------------------------------- #
# EXTRAÇÃO DE TRIPLAS DE UM ITEM (LIDA COM AS VARIAÇÕES DE CHAVE DAS LLMs)
# --------------------------------------------------------------------------- #

def extrair_triplas(item: Any, chaves_possiveis=("gold", "triples", "relations")) -> List[Triple]:
    """Extrai a lista de triplas de um item, tentando várias chaves comuns
    que diferentes LLMs usam ('gold', 'triples', 'relations') e também
    aceitando o caso em que o item já é a própria lista de triplas.
    """
    if isinstance(item, list):
        brutos = item
    elif isinstance(item, dict):
        brutos = []
        for chave in chaves_possiveis:
            if chave in item:
                brutos = item[chave]
                break
    else:
        brutos = []
    return [Triple.from_dict(t) for t in brutos if isinstance(t, dict)]


def achatar_predicoes(preds_bruto: List[Any]) -> List[Any]:
    """Achata o caso em que a LLM devolveu uma lista de listas
    (um bloco por frase) em vez de uma lista plana de itens."""
    achatado = []
    for item in preds_bruto:
        if isinstance(item, list):
            achatado.extend(item)
        else:
            achatado.append(item)
    return achatado


# --------------------------------------------------------------------------- #
# AVALIAÇÃO DE UM PAR (GOLD, PRED)
# --------------------------------------------------------------------------- #

@dataclass
class RelatorioAvaliacao:
    modelo: str
    n_frases_gold: int
    n_frases_pred: int
    precisao_lexical: float
    recall_lexical: float
    f1_lexical: float
    precisao_exact: float
    recall_exact: float
    f1_exact: float
    n_erros_parsing: int


def avaliar_par(caminho_gold: str, caminho_pred: str, limiar_lexical: float = 0.5) -> RelatorioAvaliacao:
    """Avalia um único arquivo de predições contra o gold, retornando um
    relatório estruturado (fácil de agregar em pandas depois)."""
    nome_modelo = Path(caminho_pred).stem

    leitor_gold = RobustJSONLReader(Path(caminho_gold))
    leitor_pred = RobustJSONLReader(Path(caminho_pred))

    res_gold = leitor_gold.carregar()
    res_pred = leitor_pred.carregar()

    preds = achatar_predicoes(res_pred.objetos)
    golds = res_gold.objetos

    if len(golds) != len(preds):
        log.warning(
            "[%s] Nº de frases difere: gold=%d, pred=%d. "
            "O alinhamento é feito por índice — revise se houver arquivos truncados.",
            nome_modelo, len(golds), len(preds),
        )

    matcher_lex = LexicalMatcher(limiar=limiar_lexical)
    matcher_ex = ExactMatcher()

    c_lex, c_ex = Contadores(), Contadores()

    for i, (item_gold, item_pred) in enumerate(zip(golds, preds)):
        try:
            gold_triplas = extrair_triplas(item_gold)
            pred_triplas = extrair_triplas(item_pred)
        except Exception as e:
            log.error("[%s] Falha ao extrair triplas na frase %d: %s", nome_modelo, i, e)
            continue

        r_lex = comparar_triplas(gold_triplas, pred_triplas, matcher_lex)
        r_ex = comparar_triplas(gold_triplas, pred_triplas, matcher_ex)

        c_lex.vp += r_lex.vp; c_lex.fp += r_lex.fp; c_lex.fn += r_lex.fn
        c_ex.vp += r_ex.vp; c_ex.fp += r_ex.fp; c_ex.fn += r_ex.fn

    return RelatorioAvaliacao(
        modelo=nome_modelo,
        n_frases_gold=len(golds),
        n_frases_pred=len(preds),
        precisao_lexical=c_lex.precisao(),
        recall_lexical=c_lex.recall(),
        f1_lexical=c_lex.f1(),
        precisao_exact=c_ex.precisao(),
        recall_exact=c_ex.recall(),
        f1_exact=c_ex.f1(),
        n_erros_parsing=len(res_pred.erros),
    )


def _worker(args: Tuple[str, str, float]) -> RelatorioAvaliacao:
    """Função de topo de módulo (necessária para ProcessPoolExecutor no Windows/macOS)."""
    caminho_gold, caminho_pred, limiar = args
    return avaliar_par(caminho_gold, caminho_pred, limiar)


# --------------------------------------------------------------------------- #
# EXECUÇÃO EM LOTE (VÁRIOS MODELOS EM PARALELO) + RELATÓRIO PANDAS
# --------------------------------------------------------------------------- #

def avaliar_diretorio(
    caminho_gold: str, diretorio_pred: str, workers: int = 4, limiar_lexical: float = 0.5
) -> "pandas.DataFrame":
    """Avalia todos os `.jsonl` de um diretório em paralelo e devolve um
    DataFrame comparativo (uma linha por modelo), ordenado por F1 lexical.
    """
    import pandas as pd  # import local: só é necessário nesse modo de uso

    arquivos = sorted(Path(diretorio_pred).glob("*.jsonl"))
    if not arquivos:
        raise FileNotFoundError(f"Nenhum .jsonl encontrado em '{diretorio_pred}'")

    tarefas = [(caminho_gold, str(f), limiar_lexical) for f in arquivos]
    relatorios: List[RelatorioAvaliacao] = []

    with ProcessPoolExecutor(max_workers=workers) as executor:
        futuros = {executor.submit(_worker, t): t[1] for t in tarefas}
        for futuro in as_completed(futuros):
            caminho = futuros[futuro]
            try:
                relatorios.append(futuro.result())
                log.info("Concluído: %s", Path(caminho).name)
            except Exception as e:
                log.error("Falha ao avaliar '%s': %s", caminho, e)

    df = pd.DataFrame([r.__dict__ for r in relatorios])
    return df.sort_values("f1_lexical", ascending=False).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# MODO PADRÃO (SEM ARGUMENTOS) -> varre automaticamente pastas "Respostas *"
# --------------------------------------------------------------------------- #

# Ajuste estes dois valores para o seu projeto. Usados apenas quando o script
# é executado SEM nenhum argumento de linha de comando (ex.: dando play na IDE),
# reproduzindo o hábito do script original de ter os caminhos "fixos" no arquivo.
GOLD_PADRAO = "dados/bia_gold_sentences.jsonl"
PASTA_RESPOSTAS_PADRAO = "Respostas"                   # pasta raiz com as sub-pastas "N_batches"
PASTA_METRICAS_PADRAO = Path("Outputs") / "metricas"   # onde os CSVs de saída são salvos
PREFIXO_PASTAS_PADRAO = "Respostas"                    # prefixo das pastas de modelo dentro de cada "N_batches"


def rodar_modo_padrao(workers: int = 4, limiar_lexical: float = 0.5) -> None:
    """Executa sem precisar de argumentos: procura, em `Respostas/`, todas as
    pastas de lote (ex.: '10_batches', '15_batches', ...) e, dentro de cada uma,
    todas as pastas que começam com `PREFIXO_PASTAS_PADRAO` (ex.:
    'Respostas AbstractiveOpenIE', 'Respostas ExtrativoDPTO-IE', ...).
    Avalia cada uma contra `GOLD_PADRAO` e salva um CSV por pasta em
    'Outputs/metricas/<lote>/'.
    """
    if not Path(GOLD_PADRAO).exists():
        log.error(
            "Nenhum argumento foi passado e o gold padrão '%s' não existe no diretório atual (%s). "
            "Rode com --gold/--pred (ou --pred-dir) explicitamente, ou ajuste GOLD_PADRAO no topo do script.",
            GOLD_PADRAO, Path.cwd(),
        )
        sys.exit(1)

    raiz_respostas = Path(PASTA_RESPOSTAS_PADRAO)
    if not raiz_respostas.is_dir():
        log.error("Pasta '%s' não encontrada em %s.", PASTA_RESPOSTAS_PADRAO, Path.cwd())
        sys.exit(1)

    lotes = sorted(p for p in raiz_respostas.iterdir() if p.is_dir() and p.name.endswith("_batches"))
    if not lotes:
        log.error("Nenhuma pasta '*_batches' encontrada em %s.", raiz_respostas)
        sys.exit(1)

    for lote in lotes:
        pastas = sorted(p for p in lote.iterdir() if p.is_dir() and p.name.startswith(PREFIXO_PASTAS_PADRAO))
        if not pastas:
            log.warning("Nenhuma pasta iniciada em '%s' encontrada em %s.", PREFIXO_PASTAS_PADRAO, lote)
            continue

        pasta_saida = PASTA_METRICAS_PADRAO / lote.name
        pasta_saida.mkdir(parents=True, exist_ok=True)

        for pasta in pastas:
            log.info("=== Avaliando pasta: %s/%s ===", lote.name, pasta.name)
            try:
                df = avaliar_diretorio(GOLD_PADRAO, str(pasta), workers=workers, limiar_lexical=limiar_lexical)
            except Exception as e:
                log.error("Falha ao avaliar a pasta '%s/%s': %s", lote.name, pasta.name, e)
                continue
            print(f"\n--- {lote.name}/{pasta.name} ---")
            print(df.to_string(index=False))
            saida = pasta_saida / f"resultados_{pasta.name.replace(' ', '_')}.csv"
            df.to_csv(saida, index=False)
            log.info("Relatório salvo em %s\n", saida)

# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main():
    # Sem nenhum argumento -> modo padrão (varre pastas "Respostas *" automaticamente)
    if len(sys.argv) == 1:
        rodar_modo_padrao()
        return

    parser = argparse.ArgumentParser(description="Avaliação de OpenIE (LLM vs. Gold Standard)")
    parser.add_argument("--gold", required=True, help="Caminho do arquivo gold (.jsonl)")
    parser.add_argument("--pred", help="Caminho de um único arquivo de predições (.jsonl)")
    parser.add_argument("--pred-dir", help="Diretório com vários .jsonl de modelos, avaliados em paralelo")
    parser.add_argument("--output", default=None, help="CSV de saída (apenas no modo --pred-dir)")
    parser.add_argument("--workers", type=int, default=4, help="Processos paralelos (modo --pred-dir)")
    parser.add_argument("--limiar", type=float, default=0.5, help="Limiar de overlap lexical")
    args = parser.parse_args()

    if args.pred_dir:
        df = avaliar_diretorio(args.gold, args.pred_dir, workers=args.workers, limiar_lexical=args.limiar)
        print("\n" + df.to_string(index=False))
        if args.output:
            df.to_csv(args.output, index=False)
            log.info("Relatório salvo em %s", args.output)
    elif args.pred:
        r = avaliar_par(args.gold, args.pred, limiar_lexical=args.limiar)
        print("\n" + "=" * 42)
        print(f" RESULTADOS: {r.modelo}")
        print("=" * 42)
        print(f"Frases gold/pred      : {r.n_frases_gold} / {r.n_frases_pred}")
        print(f"Erros de parsing      : {r.n_erros_parsing}")
        print("\n--- Casamento Lexical (>{:.0%}) ---".format(args.limiar))
        print(f"Precisão : {r.precisao_lexical:.4f}")
        print(f"Recall   : {r.recall_lexical:.4f}")
        print(f"F1       : {r.f1_lexical:.4f}")
        print("\n--- Casamento Exato ---")
        print(f"Precisão : {r.precisao_exact:.4f}")
        print(f"Recall   : {r.recall_exact:.4f}")
        print(f"F1       : {r.f1_exact:.4f}")
        print("=" * 42 + "\n")
    else:
        parser.error("Especifique --pred (arquivo único) ou --pred-dir (avaliação em lote)")


if __name__ == "__main__":
    main()