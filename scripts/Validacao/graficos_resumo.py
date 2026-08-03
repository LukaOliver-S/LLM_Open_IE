"""
graficos_resumo.py
===================
Gera 3 visualizações para separar "cobertura" de "qualidade" e entender o
trade-off precisão/recall, cruzando todas as pastas Respostas/<N>_batches/*.

1. cobertura_vs_f1.png   -- scatter: % de frases cobertas x F1 condicional
2. cobertura_barras.png  -- barras empilhadas: cobertas x faltando, por modelo/tarefa
3. precisao_vs_recall.png -- scatter: precisão x recall, com diagonal de equilíbrio

Uso: `python graficos_resumo.py` (sem argumentos).
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict
import re
import pandas as pd
import matplotlib.pyplot as plt

from resultados import (
    log,
    RobustJSONLReader,
    achatar_predicoes,
    extrair_triplas,
    comparar_triplas,
    LexicalMatcher,
    Contadores,
    _normalizar_sentenca,
    CORPORA,
    CORPUS_PADRAO,
    resolver_corpus,
)

MARCADORES = ["o", "s", "^", "D", "v", "P"]
_RE_PREFIXO_MODELO = re.compile(r"^respostas?_?", re.IGNORECASE)

parser = argparse.ArgumentParser()
parser.add_argument("--corpus", default=CORPUS_PADRAO, choices=list(CORPORA),
                    help="Corpus (define gold + pastas). Default: %(default)s")
parser.add_argument("--lotes", type=int, default=None,
                    help="Processar só este tamanho de lote (ex.: 25). Se omitido, processa todos.")
args = parser.parse_args()

def _nome_curto(modelo: str) -> str:
    """Remove o prefixo redundante 'resposta(s)_' dos nomes de modelo."""
    return _RE_PREFIXO_MODELO.sub("", modelo)
def avaliar_condicional(caminho_gold: str, caminho_pred: str, limiar_lexical: float = 0.5) -> Dict[str, Any]:
    """Como `avaliar_par`, mas SEM penalizar sentenças do gold nunca cobertas
    -- mede a qualidade só onde o modelo respondeu; a cobertura é reportada
    à parte, sem se misturar ao score."""
    nome_modelo = Path(caminho_pred).stem

    golds = RobustJSONLReader(Path(caminho_gold)).carregar().objetos
    preds = achatar_predicoes(RobustJSONLReader(Path(caminho_pred)).carregar().objetos)

    gold_por_sentenca = {
        _normalizar_sentenca(g.get("sentence", "") if isinstance(g, dict) else ""): g
        for g in golds
    }

    matcher_lex = LexicalMatcher(limiar=limiar_lexical)
    c_lex = Contadores()
    n_pareadas = 0

    for item_pred in preds:
        chave = _normalizar_sentenca(item_pred.get("sentence", "") if isinstance(item_pred, dict) else "")
        item_gold = gold_por_sentenca.get(chave)
        if item_gold is None:
            continue
        triplas_pred = extrair_triplas(item_pred)
        if not triplas_pred:            # devolveu a frase mas SEM tripla -> nao conta como coberta
            continue
        n_pareadas += 1
        r = comparar_triplas(extrair_triplas(item_gold), triplas_pred, matcher_lex)
        c_lex.vp += r.vp; c_lex.fp += r.fp; c_lex.fn += r.fn

    n_frases_gold = len(golds)
    return {
        "modelo": nome_modelo,
        "n_frases_gold": n_frases_gold,
        "n_frases_pareadas": n_pareadas,
        "cobertura": n_pareadas / n_frases_gold if n_frases_gold else 0.0,
        "precisao_lexical": c_lex.precisao(),
        "recall_lexical": c_lex.recall(),
        "f1_lexical": c_lex.f1(),
    }


def plotar_cobertura_vs_f1(df: pd.DataFrame, caminho_png: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 6))
    for i, cat in enumerate(sorted(df["categoria"].unique())):
        d = df[df["categoria"] == cat]
        ax.scatter(d["cobertura"] * 100, d["f1_lexical"], label=cat,
                   marker=MARCADORES[i % len(MARCADORES)], s=80)
        for _, row in d.iterrows():
            ax.annotate(row["modelo"], (row["cobertura"] * 100, row["f1_lexical"]),
                        fontsize=7, xytext=(4, 4), textcoords="offset points")
    ax.set_xlabel("Cobertura (% de frases realmente respondidas)")
    ax.set_ylabel("F1 lexical (condicional às frases cobertas)")
    ax.set_title("Cobertura x Qualidade condicional, por modelo e tarefa")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(caminho_png, dpi=150)
    plt.close(fig)


def plotar_cobertura_barras(df: pd.DataFrame, caminho_png: Path) -> None:
    d = df.copy()
    d["cobertura_pct"] = d["cobertura"] * 100
    d["faltando_pct"] = 100 - d["cobertura_pct"]
    d["rotulo"] = d["modelo"].map(_nome_curto) + " (" + d["categoria"] + ")"
    d = d.sort_values("cobertura_pct", ascending=True)

    fig, ax = plt.subplots(figsize=(max(8, 0.6 * len(d)), 5))
    x = range(len(d))
    ax.bar(x, d["cobertura_pct"], label="Cobertas", color="#2ca02c")
    ax.bar(x, d["faltando_pct"], bottom=d["cobertura_pct"], label="Faltando", color="#d62728")

    for i, (_, row) in enumerate(d.iterrows()):
        ax.text(i, 102, f'{row["cobertura_pct"]:.0f}%', ha="center", fontsize=8)

    ax.set_xticks(list(x))
    ax.set_xticklabels(d["rotulo"], rotation=45, ha="right", fontsize=8)
    ax.set_ylim(0, 112)
    ax.set_ylabel("% de frases")
    ax.set_title("Cobertura de sentenças por modelo e tarefa (ordenado, pior primeiro)")
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(caminho_png, dpi=150)
    plt.close(fig)


def plotar_precisao_recall(df: pd.DataFrame, caminho_png: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 7))
    for i, cat in enumerate(sorted(df["categoria"].unique())):
        d = df[df["categoria"] == cat]
        ax.scatter(d["precisao_lexical"], d["recall_lexical"], label=cat,
                   marker=MARCADORES[i % len(MARCADORES)], s=80)
        for _, row in d.iterrows():
            ax.annotate(row["modelo"], (row["precisao_lexical"], row["recall_lexical"]),
                        fontsize=7, xytext=(4, 4), textcoords="offset points")
    lim = max(df["precisao_lexical"].max(), df["recall_lexical"].max()) * 1.1
    ax.plot([0, lim], [0, lim], linestyle="--", color="#333333", linewidth=1, label="Precisão = Recall")
    ax.set_xlim(0, lim)
    ax.set_ylim(0, lim)
    ax.set_xlabel("Precisão lexical")
    ax.set_ylabel("Recall lexical")
    ax.set_title("Precisão x Recall, por modelo e tarefa")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(caminho_png, dpi=150)
    plt.close(fig)


def main() -> None:
    cfg = resolver_corpus(args.corpus)
    gold = cfg["gold"]
    raiz_respostas = Path(cfg["respostas"])
    raiz_metricas = cfg["saida"]

    lotes = sorted(p for p in raiz_respostas.iterdir() if p.is_dir() and p.name.endswith("_batches"))
    if args.lotes is not None:
     lotes = [p for p in lotes if p.name == f"{args.lotes}_batches"]
    if not lotes:
        raise FileNotFoundError(f"Pasta 'Respostas/{args.lotes}_batches' não encontrada.")
    for lote in lotes:
        pastas = sorted(p for p in lote.iterdir() if p.is_dir() and p.name.startswith("Respostas"))
        if not pastas:
            continue

        linhas = []
        for pasta in pastas:
            categoria = pasta.name.replace("Respostas ", "").replace("Respostas", "").strip() or pasta.name
            for arquivo in sorted(pasta.glob("*.jsonl")):
                try:
                    r = avaliar_condicional(gold, str(arquivo))
                except Exception as e:
                    log.error("Falha ao avaliar '%s': %s", arquivo, e)
                    continue
                r["categoria"] = categoria
                linhas.append(r)

        if not linhas:
            continue
        df = pd.DataFrame(linhas)

        pasta_saida = raiz_metricas / lote.name / "graficos_resumo"
        pasta_saida.mkdir(parents=True, exist_ok=True)

        df.to_csv(pasta_saida / "resumo_cobertura_qualidade.csv", index=False)
        plotar_cobertura_vs_f1(df, pasta_saida / "cobertura_vs_f1.png")
        plotar_cobertura_barras(df, pasta_saida / "cobertura_barras.png")
        plotar_precisao_recall(df, pasta_saida / "precisao_vs_recall.png")
        log.info("Gráficos e CSV salvos em %s", pasta_saida)


if __name__ == "__main__":
    main()