#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gerar_graficos.py
==================

Gera gráficos prontos para artigo científico a partir dos CSVs de saída do
`resultados.py` (colunas: modelo, n_frases_gold, n_frases_pred,
precisao_lexical, recall_lexical, f1_lexical, precisao_exact, recall_exact,
f1_exact, n_erros_parsing).

Gráficos gerados (para CADA csv de entrada):
  1. <base>_f1_lexical.png/.pdf   -> barras horizontais de F1 lexical, ordenado
  2. <base>_prec_rec_f1.png/.pdf  -> barras agrupadas Precisão/Recall/F1 (lexical)
  3. <base>_lexical_vs_exact.png/.pdf -> barras agrupadas F1 lexical vs F1 exato

Se você passar MAIS DE UM csv (ex.: um por pasta/tarefa: Abstractive,
ExtrativoDPTO-IE, ExtrativoOIEC-PT), também gera:
  4. comparativo_tarefas_f1_lexical.png/.pdf -> um gráfico só comparando
     todos os modelos em todas as tarefas lado a lado.

USO
----
    # Um csv só
    python3 gerar_graficos.py resultados_Respostas_AbstractiveOpenIE.csv

    # Vários csvs (compara também entre tarefas)
    python3 gerar_graficos.py resultados_*.csv --saida figuras/

    # Escolher quais métricas focar / ordenar
    python3 gerar_graficos.py resultados.csv --metrica f1_exact

Requer: pandas, matplotlib (pip install pandas matplotlib --break-system-packages)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

import matplotlib

matplotlib.use("Agg")  # não precisa de display, só salvar arquivo
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd

# --------------------------------------------------------------------------- #
# ESTILO "PAPER" (fonte serifada, preto e branco / poucas cores, sem grade pesada)
# --------------------------------------------------------------------------- #

plt.rcParams.update({
    "font.family": "serif",
    "font.size": 11,
    "axes.titlesize": 12,
    "axes.labelsize": 11,
    "axes.edgecolor": "#333333",
    "axes.linewidth": 0.8,
    "axes.grid": True,
    "grid.color": "#dddddd",
    "grid.linewidth": 0.6,
    "figure.dpi": 150,
    "savefig.dpi": 300,
    "legend.frameon": False,
})

PALETA = ["#2c3e50", "#2980b9", "#27ae60", "#e67e22", "#c0392b", "#8e44ad", "#16a085"]


def salvar(fig: plt.Figure, caminho_base: Path) -> None:
    """Salva a figura em PNG (300dpi, para Word/PowerPoint) e PDF (vetorial,
    para LaTeX). Mantém a mesma figura, só troca o formato do arquivo."""
    fig.savefig(caminho_base.with_suffix(".png"), bbox_inches="tight")
    fig.savefig(caminho_base.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)
    print(f"   -> {caminho_base.with_suffix('.png')}")
    print(f"   -> {caminho_base.with_suffix('.pdf')}")


def rotular_barras(ax, barras, formato="{:.3f}", offset=0.01):
    """Escreve o valor no topo/ponta de cada barra."""
    for b in barras:
        largura = b.get_width()
        altura = b.get_height()
        if largura and not altura:  # barra horizontal
            ax.text(largura + offset, b.get_y() + b.get_height() / 2,
                     formato.format(largura), va="center", fontsize=9)
        elif altura:  # barra vertical
            ax.text(b.get_x() + b.get_width() / 2, altura + offset,
                     formato.format(altura), ha="center", fontsize=9)


# --------------------------------------------------------------------------- #
# GRÁFICO 1: F1 lexical, barras horizontais ordenadas
# --------------------------------------------------------------------------- #

def grafico_f1_ordenado(df: pd.DataFrame, metrica: str, titulo: str, caminho_base: Path):
    d = df.sort_values(metrica, ascending=True)
    fig, ax = plt.subplots(figsize=(7, 0.55 * len(d) + 1.2))
    barras = ax.barh(d["modelo"], d[metrica], color=PALETA[1], edgecolor="#1a2530", linewidth=0.6)
    rotular_barras(ax, barras)
    ax.set_xlabel(titulo)
    ax.set_xlim(0, max(d[metrica].max() * 1.2, 0.1))
    ax.set_title(titulo)
    ax.xaxis.set_major_formatter(mticker.FormatStrFormatter("%.2f"))
    fig.tight_layout()
    salvar(fig, caminho_base)


# --------------------------------------------------------------------------- #
# GRÁFICO 2: Precisão / Recall / F1 (lexical) agrupados por modelo
# --------------------------------------------------------------------------- #

def grafico_prf_agrupado(df: pd.DataFrame, caminho_base: Path, sufixo="lexical"):
    d = df.sort_values(f"f1_{sufixo}", ascending=False)
    modelos = d["modelo"].tolist()
    x = range(len(modelos))
    largura = 0.25

    fig, ax = plt.subplots(figsize=(max(7, 1.1 * len(modelos)), 4.5))
    b1 = ax.bar([i - largura for i in x], d[f"precisao_{sufixo}"], largura, label="Precisão", color=PALETA[0])
    b2 = ax.bar(list(x), d[f"recall_{sufixo}"], largura, label="Recall", color=PALETA[1])
    b3 = ax.bar([i + largura for i in x], d[f"f1_{sufixo}"], largura, label="F1", color=PALETA[2])

    ax.set_xticks(list(x))
    ax.set_xticklabels(modelos, rotation=30, ha="right")
    ax.set_ylabel(f"Pontuação ({'Casamento Lexical' if sufixo == 'lexical' else 'Casamento Exato'})")
    ax.set_ylim(0, 1.0)
    ax.legend(loc="upper right", ncol=3)
    ax.set_title(f"Precisão, Recall e F1 por modelo — {'Casamento Lexical' if sufixo == 'lexical' else 'Casamento Exato'}")
    fig.tight_layout()
    salvar(fig, caminho_base)


# --------------------------------------------------------------------------- #
# GRÁFICO 3: F1 lexical vs F1 exato, agrupados por modelo
# --------------------------------------------------------------------------- #

def grafico_lexical_vs_exact(df: pd.DataFrame, caminho_base: Path):
    d = df.sort_values("f1_lexical", ascending=False)
    modelos = d["modelo"].tolist()
    x = range(len(modelos))
    largura = 0.35

    fig, ax = plt.subplots(figsize=(max(7, 1.1 * len(modelos)), 4.5))
    b1 = ax.bar([i - largura / 2 for i in x], d["f1_lexical"], largura, label="F1 (Lexical > 50%)", color=PALETA[1])
    b2 = ax.bar([i + largura / 2 for i in x], d["f1_exact"], largura, label="F1 (Exato)", color=PALETA[4])

    ax.set_xticks(list(x))
    ax.set_xticklabels(modelos, rotation=30, ha="right")
    ax.set_ylabel("F1-Score")
    ax.set_ylim(0, 1.0)
    ax.legend(loc="upper right")
    ax.set_title("F1-Score: Casamento Lexical vs. Casamento Exato")
    fig.tight_layout()
    salvar(fig, caminho_base)


# --------------------------------------------------------------------------- #
# GRÁFICO 4 (múltiplos csvs): comparação entre tarefas
# --------------------------------------------------------------------------- #

def grafico_comparativo_tarefas(dfs_por_tarefa: dict, metrica: str, caminho_base: Path):
    """dfs_por_tarefa: {nome_da_tarefa: DataFrame}"""
    tarefas = list(dfs_por_tarefa.keys())
    modelos = sorted({m for df in dfs_por_tarefa.values() for m in df["modelo"]})

    x = range(len(modelos))
    n_tarefas = len(tarefas)
    largura = 0.8 / n_tarefas

    fig, ax = plt.subplots(figsize=(max(8, 1.3 * len(modelos)), 5))
    for i, tarefa in enumerate(tarefas):
        df = dfs_por_tarefa[tarefa].set_index("modelo")
        valores = [df.loc[m, metrica] if m in df.index else 0 for m in modelos]
        offset = (i - (n_tarefas - 1) / 2) * largura
        ax.bar([xi + offset for xi in x], valores, largura, label=tarefa, color=PALETA[i % len(PALETA)])

    ax.set_xticks(list(x))
    ax.set_xticklabels(modelos, rotation=30, ha="right")
    ax.set_ylabel(metrica.replace("_", " ").title())
    ax.set_ylim(0, 1.0)
    ax.legend(loc="upper right", title="Tarefa")
    ax.set_title(f"Comparação entre tarefas — {metrica.replace('_', ' ').title()}")
    fig.tight_layout()
    salvar(fig, caminho_base)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser(description="Gera gráficos para artigo a partir dos CSVs do resultados.py")
    parser.add_argument("csvs", nargs="+", help="Um ou mais arquivos resultados_*.csv")
    parser.add_argument("--saida", default="figuras", help="Pasta de saída (default: ./figuras)")
    parser.add_argument("--metrica", default="f1_lexical",
                         help="Métrica usada no gráfico de barras ordenado e na comparação entre tarefas "
                              "(default: f1_lexical). Ex.: f1_exact, precisao_lexical, recall_lexical")
    args = parser.parse_args()

    pasta_saida = Path(args.saida)
    pasta_saida.mkdir(parents=True, exist_ok=True)

    dfs_por_tarefa = {}

    for caminho_csv in args.csvs:
        caminho_csv = Path(caminho_csv)
        if not caminho_csv.exists():
            print(f"❌ Não encontrado, pulando: {caminho_csv}")
            continue

        df = pd.read_csv(caminho_csv)
        nome_tarefa = caminho_csv.stem.replace("resultados_", "").replace("_", " ")
        print(f"\n📊 Gerando gráficos para: {nome_tarefa}")

        base = pasta_saida / caminho_csv.stem
        grafico_f1_ordenado(df, args.metrica, f"{args.metrica.replace('_', ' ').title()} — {nome_tarefa}",
                             base.with_name(base.name + f"_{args.metrica}_ordenado"))
        grafico_prf_agrupado(df, base.with_name(base.name + "_prec_rec_f1_lexical"), sufixo="lexical")
        grafico_prf_agrupado(df, base.with_name(base.name + "_prec_rec_f1_exact"), sufixo="exact")
        grafico_lexical_vs_exact(df, base.with_name(base.name + "_lexical_vs_exact"))

        dfs_por_tarefa[nome_tarefa] = df

    if len(dfs_por_tarefa) > 1:
        print(f"\n📊 Gerando gráfico comparativo entre {len(dfs_por_tarefa)} tarefas...")
        grafico_comparativo_tarefas(dfs_por_tarefa, args.metrica, pasta_saida / f"comparativo_tarefas_{args.metrica}")

    print(f"\n✅ Todos os gráficos foram salvos em: {pasta_saida.resolve()}")


if __name__ == "__main__":
    main()