#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
contagem_triplas.py
====================

Compara, por modelo, quantas triplas (relações) foram extraídas em relação
ao gold standard -- para diagnosticar se um modelo com F1 baixo está
SUBGERANDO (poucas triplas, recall baixo) ou SUPERGERANDO (muitas triplas
erradas, precisão baixa) relações.

Reaproveita a leitura/parsing de `resultados.py` (RobustJSONLReader,
achatar_predicoes, extrair_triplas, _normalizar_sentenca) -- só muda o que
é agregado no final. Também gera gráficos (PNG + PDF) comparando
triplas gold x preditas e a razão pred/gold por modelo.

Uso: `python contagem_triplas.py` (sem argumentos). Varre as mesmas pastas
`Respostas/<N>_batches/Respostas */` que o modo padrão de `resultados.py`
e salva, por pasta, um CSV e dois gráficos em
`Outputs/metricas/<lote>/graficos/`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from resultados import (
    log,
    RobustJSONLReader,
    achatar_predicoes,
    extrair_triplas,
    _normalizar_sentenca,
)

GOLD_PADRAO = "dados/bia_gold_sentences.jsonl"
PASTA_RESPOSTAS_PADRAO = "Respostas"
PASTA_METRICAS_PADRAO = Path("Outputs") / "metricas"
PREFIXO_PASTAS_PADRAO = "Respostas"

# --------------------------------------------------------------------------- #
# ESTILO "PAPER" (mesmo estilo de gerar_graficos.py)
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


def _salvar(fig: plt.Figure, caminho_base: Path) -> None:
    fig.savefig(caminho_base.with_suffix(".png"), bbox_inches="tight")
    fig.savefig(caminho_base.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)
    print(f"   -> {caminho_base.with_suffix('.png')}")
    print(f"   -> {caminho_base.with_suffix('.pdf')}")


# --------------------------------------------------------------------------- #
# CONTAGEM
# --------------------------------------------------------------------------- #

def contar_triplas(caminho_gold: str, caminho_pred: str) -> Dict[str, Any]:
    """Conta triplas gold x preditas para um único arquivo de modelo,
    pareando sentenças por texto (mesma lógica de `avaliar_par`)."""
    nome_modelo = Path(caminho_pred).stem

    golds = RobustJSONLReader(Path(caminho_gold)).carregar().objetos
    preds = achatar_predicoes(RobustJSONLReader(Path(caminho_pred)).carregar().objetos)

    gold_por_sentenca = {
        _normalizar_sentenca(g.get("sentence", "") if isinstance(g, dict) else ""): g
        for g in golds
    }

    n_triplas_gold_total = sum(len(extrair_triplas(g)) for g in golds)

    n_pareadas = 0
    n_triplas_gold_pareadas = 0
    n_triplas_pred = 0

    for item_pred in preds:
        chave = _normalizar_sentenca(item_pred.get("sentence", "") if isinstance(item_pred, dict) else "")
        item_gold = gold_por_sentenca.get(chave)
        if item_gold is None:
            continue
        n_pareadas += 1
        n_triplas_gold_pareadas += len(extrair_triplas(item_gold))
        n_triplas_pred += len(extrair_triplas(item_pred))

    media_gold = n_triplas_gold_pareadas / n_pareadas if n_pareadas else 0.0
    media_pred = n_triplas_pred / n_pareadas if n_pareadas else 0.0
    razao_pred_gold = n_triplas_pred / n_triplas_gold_pareadas if n_triplas_gold_pareadas else 0.0

    return {
        "modelo": nome_modelo,
        "n_frases_gold_total": len(golds),
        "n_frases_pred": len(preds),
        "n_frases_pareadas": n_pareadas,
        "n_triplas_gold_total": n_triplas_gold_total,
        "n_triplas_gold_pareadas": n_triplas_gold_pareadas,
        "n_triplas_pred": n_triplas_pred,
        "media_triplas_gold_por_frase": media_gold,
        "media_triplas_pred_por_frase": media_pred,
        "razao_pred_gold": razao_pred_gold,
    }


def contar_diretorio(caminho_gold: str, diretorio_pred: str) -> pd.DataFrame:
    """Roda `contar_triplas` para todos os `.jsonl` de uma pasta (um modelo
    por arquivo) e devolve um DataFrame ordenado por razão pred/gold."""
    arquivos = sorted(Path(diretorio_pred).glob("*.jsonl"))
    if not arquivos:
        raise FileNotFoundError(f"Nenhum .jsonl encontrado em '{diretorio_pred}'")

    linhas = []
    for f in arquivos:
        try:
            linhas.append(contar_triplas(caminho_gold, str(f)))
        except Exception as e:
            log.error("Falha ao contar triplas em '%s': %s", f, e)

    df = pd.DataFrame(linhas)
    return df.sort_values("razao_pred_gold", ascending=False).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# GRÁFICOS
# --------------------------------------------------------------------------- #

def grafico_gold_vs_pred(df: pd.DataFrame, titulo: str, caminho_base: Path) -> None:
    """Barras agrupadas: triplas gold (pareadas) x triplas preditas, por modelo."""
    d = df.sort_values("razao_pred_gold", ascending=False)
    modelos = d["modelo"].tolist()
    x = range(len(modelos))
    largura = 0.35

    fig, ax = plt.subplots(figsize=(max(7, 1.1 * len(modelos)), 4.5))
    ax.bar([i - largura / 2 for i in x], d["n_triplas_gold_pareadas"], largura,
           label="Gold", color=PALETA[0])
    ax.bar([i + largura / 2 for i in x], d["n_triplas_pred"], largura,
           label="Predito", color=PALETA[1])

    ax.set_xticks(list(x))
    ax.set_xticklabels(modelos, rotation=30, ha="right")
    ax.set_ylabel("Número de triplas")
    ax.legend(loc="upper right")
    ax.set_title(titulo)
    fig.tight_layout()
    _salvar(fig, caminho_base)


def grafico_razao_pred_gold(df: pd.DataFrame, titulo: str, caminho_base: Path) -> None:
    """Barras da razão triplas_pred / triplas_gold por modelo, com linha de
    referência em 1.0 (acima = supergeração, abaixo = subgeração)."""
    d = df.sort_values("razao_pred_gold", ascending=False)
    cores = [PALETA[4] if v > 1 else PALETA[2] for v in d["razao_pred_gold"]]

    fig, ax = plt.subplots(figsize=(max(7, 1.1 * len(d)), 4.5))
    barras = ax.bar(d["modelo"], d["razao_pred_gold"], color=cores, edgecolor="#1a2530", linewidth=0.6)
    ax.axhline(1.0, color="#333333", linestyle="--", linewidth=1, label="Equilíbrio (pred = gold)")

    for b in barras:
        altura = b.get_height()
        ax.text(b.get_x() + b.get_width() / 2, altura + 0.02, f"{altura:.2f}",
                 ha="center", fontsize=9)

    ax.set_xticklabels(d["modelo"], rotation=30, ha="right")
    ax.set_ylabel("Razão triplas preditas / triplas gold")
    ax.set_title(titulo)
    ax.legend(loc="upper right")
    fig.tight_layout()
    _salvar(fig, caminho_base)


# --------------------------------------------------------------------------- #
# MODO PADRÃO
# --------------------------------------------------------------------------- #

def main() -> None:
    if not Path(GOLD_PADRAO).exists():
        log.error("Gold padrão '%s' não encontrado em %s.", GOLD_PADRAO, Path.cwd())
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
            continue

        pasta_saida = PASTA_METRICAS_PADRAO / lote.name
        pasta_saida.mkdir(parents=True, exist_ok=True)
        pasta_graficos = pasta_saida / "graficos_relations"
        pasta_graficos.mkdir(parents=True, exist_ok=True)

        for pasta in pastas:
            log.info("=== Contando triplas: %s/%s ===", lote.name, pasta.name)
            try:
                df = contar_diretorio(GOLD_PADRAO, str(pasta))
            except Exception as e:
                log.error("Falha ao processar a pasta '%s/%s': %s", lote.name, pasta.name, e)
                continue

            print(f"\n--- {lote.name}/{pasta.name} ---")
            print(df.to_string(index=False))

            nome_base = pasta.name.replace(" ", "_")
            saida_csv = pasta_saida / f"contagem_triplas_{nome_base}.csv"
            df.to_csv(saida_csv, index=False)
            log.info("CSV salvo em %s", saida_csv)

            grafico_gold_vs_pred(
                df, f"Triplas Gold x Preditas — {pasta.name}",
                pasta_graficos / f"gold_vs_pred_{nome_base}",
            )
            grafico_razao_pred_gold(
                df, f"Razão Predito/Gold — {pasta.name}",
                pasta_graficos / f"razao_pred_gold_{nome_base}",
            )


if __name__ == "__main__":
    main()