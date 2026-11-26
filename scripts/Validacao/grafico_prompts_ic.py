#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
grafico_prompts_ic.py
======================

Gráficos do efeito do prompt sobre o F1 de cada LLM, a partir dos CSVs do `bootstrap_ic.py`.

  1. f1_por_prompt_<metrica>.png/.pdf
        Barras agrupadas: eixo x = LLM, uma barra por prompt, barra de erro = IC 95% do bootstrap por sentença.
        Valor (F1) escrito acima de cada barra, sem linhas de grade.
  2. efeito_vs_semregras_<metrica>.png/.pdf
        Para cada LLM e cada prompt de regras, a diferença de F1 contra o prompt SemRegras, com IC 95% pareado.
        Pontos cheios = IC exclui zero (distinguível), pontos vazados = IC inclui zero.

Só entram os sistemas LLM (pastas Respostas* com prompt). Sistemas extrativos locais (PTOIE-Flair, T5, etc.)
ficam de fora, pois não variam de prompt.

USO (da raiz do repositório)
    python scripts/Validacao/grafico_prompts_ic.py --corpus bia
    python scripts/Validacao/grafico_prompts_ic.py --corpus bia oiec_pt --metrica exact
Entrada: Outputs/bootstrap/<corpus>/ic_<metrica>.csv e prompt_vs_semregras_<metrica>.csv
Saída:   Outputs/bootstrap/<corpus>/graficos/
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

plt.rcParams.update({
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.labelsize": 11,
    "axes.edgecolor": "#333333",
    "axes.linewidth": 0.8,
    "axes.grid": False,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.dpi": 120,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
})

# ordem e rótulos dos prompts (a pasta vem do bootstrap_ic: "ExtrativoDPTO-IE", "SemRegras", ...)
ORDEM_PROMPTS = ["SemRegras", "ExtrativoDPTO-IE", "ExtrativoOIEC-PT", "ExtrativoOIEC-PT-simples", "ExtrativoPTOIE-DP",
                 "ExtrativoBIA-completo", "ExtrativoBIA"]
ROTULO = {
    "SemRegras": "Sem regras",
    "ExtrativoDPTO-IE": "DPTO-IE",
    "ExtrativoOIEC-PT": "OIEC-PT",
    "ExtrativoOIEC-PT-simples": "OIEC-PT (simples)",
    "ExtrativoPTOIE-DP": "PTOIE-DP",
    "ExtrativoBIA-completo": "BIA",
    "ExtrativoBIA": "BIA (simples)",
}
COR = {
    "SemRegras": "#9e9e9e",
    "ExtrativoDPTO-IE": "#4c78a8",
    "ExtrativoOIEC-PT": "#f58518",
    "ExtrativoOIEC-PT-simples": "#f9c784",
    "ExtrativoPTOIE-DP": "#54a24b",
    "ExtrativoBIA-completo": "#b279a2",
    "ExtrativoBIA": "#e7a8d0",
}
ROTULO_LLM = {"Claude_Sonnet5": "Claude Sonnet 5", "GeminiHydrogen4": "Gemini Hydrogen 4",
              "Grok4.0Fast": "Grok 4.0 Fast", "gpt5.5_mini": "GPT-5.5 mini", "Gemini3.1Pro": "Gemini 3.1 Pro"}


def salvar(fig, base: Path) -> None:
    for ext in ("png", "pdf"):
        fig.savefig(base.with_suffix(f".{ext}"))
    plt.close(fig)
    print("  gravado:", base.with_suffix(".png"))


def grafico_f1(ic: pd.DataFrame, corpus: str, metrica: str, saida: Path) -> None:
    llm = ic[ic["pasta"].isin(ORDEM_PROMPTS)].copy()
    prompts = [p for p in ORDEM_PROMPTS if p in set(llm["pasta"])]
    # ordena os LLMs pelo F1 médio entre prompts
    ordem_llm = llm.groupby("canon")["f1"].mean().sort_values(ascending=False).index.tolist()

    larg = 0.8 / len(prompts)
    x = np.arange(len(ordem_llm))
    fig, ax = plt.subplots(figsize=(max(8, 1.9 * len(ordem_llm) + 2), 5))
    for j, p in enumerate(prompts):
        sub = llm[llm["pasta"] == p].set_index("canon")
        ys, lo, hi, xs = [], [], [], []
        for i, m in enumerate(ordem_llm):
            if m in sub.index:
                r = sub.loc[m]
                xs.append(x[i] + (j - (len(prompts) - 1) / 2) * larg)
                ys.append(r["f1"]); lo.append(r["f1"] - r["ic95_inf"]); hi.append(r["ic95_sup"] - r["f1"])
        barras = ax.bar(xs, ys, larg * 0.92, color=COR[p], label=ROTULO[p],
                        yerr=[lo, hi], capsize=2, error_kw={"elinewidth": 0.8, "ecolor": "#333333"})
        for b, y, h in zip(barras, ys, hi):
            ax.text(b.get_x() + b.get_width() / 2, y + h + 0.008, f"{y:.1%}", ha="center", va="bottom",
                    fontsize=7, rotation=90)
    ax.set_xticks(x)
    ax.set_xticklabels([ROTULO_LLM.get(m, m) for m in ordem_llm])
    ax.set_ylabel(f"F1 ({'lexical' if metrica == 'lexical' else 'exato'})")
    ax.set_ylim(0, min(1.0, llm["ic95_sup"].max() + 0.12))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.set_title(f"F1 por LLM e prompt, corpus {corpus} (barras: IC 95% por bootstrap de sentenças)")
    ax.legend(frameon=False, ncol=len(prompts), loc="upper center", bbox_to_anchor=(0.5, -0.08))
    salvar(fig, saida / f"f1_por_prompt_{metrica}")


def grafico_efeito(pv: pd.DataFrame, corpus: str, metrica: str, saida: Path) -> None:
    if pv.empty:
        print("  prompt_vs_semregras vazio, pulando gráfico de efeito")
        return
    prompts = [p for p in ORDEM_PROMPTS if p in set(pv["prompt"])]
    llms = pv.groupby("llm")["dif"].mean().sort_values(ascending=False).index.tolist()
    fig, ax = plt.subplots(figsize=(8, 0.55 * len(llms) * len(prompts) + 1.8))
    desloc = 0.8 / len(prompts)
    for j, p in enumerate(prompts):
        sub = pv[pv["prompt"] == p].set_index("llm")
        for i, m in enumerate(llms):
            if m not in sub.index:
                continue
            r = sub.loc[m]
            y = i + (j - (len(prompts) - 1) / 2) * desloc
            ax.errorbar(r["dif"], y, xerr=[[r["dif"] - r["ic95_inf"]], [r["ic95_sup"] - r["dif"]]],
                        fmt="o", color=COR[p], mfc=COR[p] if r["distinguivel"] else "white",
                        capsize=2, markersize=6, elinewidth=1,
                        label=ROTULO[p] if i == 0 else None)
            ax.text(r["ic95_sup"] + 0.006, y, f"{r['dif']:+.1%}", va="center", fontsize=7)
    ax.axvline(0, color="#333333", linewidth=0.8)
    ax.set_yticks(range(len(llms)))
    ax.set_yticklabels([ROTULO_LLM.get(m, m) for m in llms])
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:+.0%}"))
    ax.set_xlabel("Diferença de F1 contra o prompt sem regras (IC 95% pareado)")
    ax.set_title(f"Efeito das regras sobre cada LLM, corpus {corpus}\n(ponto cheio: IC exclui zero; vazado: inclui zero)")
    ax.legend(frameon=False, loc="lower right")
    salvar(fig, saida / f"efeito_vs_semregras_{metrica}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", nargs="*", default=["bia"])
    ap.add_argument("--metrica", choices=["lexical", "exact"], default="lexical")
    ap.add_argument("--entrada", default="Outputs/bootstrap")
    ap.add_argument("--ignorar", nargs="*", default=["ExtrativoBIA"], help="pastas de prompt a deixar de fora (padrão: BIA simples)")
    a = ap.parse_args()
    for c in a.corpus:
        pasta = Path(a.entrada) / c
        f_ic, f_pv = pasta / f"ic_{a.metrica}.csv", pasta / f"prompt_vs_semregras_{a.metrica}.csv"
        if not f_ic.exists():
            print(f"[{c}] {f_ic} não existe: rode bootstrap_ic.py antes")
            continue
        saida = pasta / "graficos"
        saida.mkdir(parents=True, exist_ok=True)
        print(f"[{c}]")
        ic_df = pd.read_csv(f_ic)
        ic_df = ic_df[~ic_df["pasta"].isin(a.ignorar)]
        pv_df = pd.read_csv(f_pv) if f_pv.exists() else pd.DataFrame()
        if len(pv_df):
            pv_df = pv_df[~pv_df["prompt"].isin(a.ignorar)]
        grafico_f1(ic_df, c, a.metrica, saida)
        grafico_efeito(pv_df, c, a.metrica, saida)


if __name__ == "__main__":
    main()
