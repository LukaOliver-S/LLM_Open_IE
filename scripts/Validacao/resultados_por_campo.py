#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
resultados_por_campo.py
=======================

Avaliação POR SLOT (arg1 / rel / arg2), em vez do casamento tudo-ou-nada de
triplas do resultados.py. Para cada campo, mede P/R/F1 comparando SÓ aquele
campo (arg1 contra arg1, rel contra rel, arg2 contra arg2), com o mesmo
casamento guloso 1-para-1 e o mesmo overlap lexical.

Saída: Outputs/metricas/<lote>/resultados_por_campo_<pasta>.csv
colunas: modelo, campo, precisao, recall, f1, vp, fp, fn
  (campo ∈ {arg1, rel, arg2, tripla_completa})

USO
    python3 resultados_por_campo.py             # todos os lotes/pastas
    python3 resultados_por_campo.py --lotes 10  # só o 10_batches
"""

from __future__ import annotations
import numpy as np
import matplotlib
matplotlib.use("Agg")               # backend sem tela (roda em qualquer lugar)
import matplotlib.pyplot as plt

# Paleta Okabe-Ito (colorblind-safe), ordem FIXA arg1 -> rel -> arg2
CORES_CAMPO = {"arg1": "#0072B2", "rel": "#E69F00", "arg2": "#009E73"}
import argparse
import csv
from pathlib import Path
from typing import Dict

from resultados import (
    RobustJSONLReader,
    achatar_predicoes,
    extrair_triplas,
    _normalizar_sentenca,
    comparar_triplas,
    Contadores,
    LexicalMatcher,
    TripleMatcher,
    CORPORA,
    CORPUS_PADRAO,
    resolver_corpus,
)

CAMPOS = ("arg1", "rel", "arg2")


class SlotMatcher(TripleMatcher):
    """Casa duas triplas olhando SÓ um slot (arg1, rel ou arg2)."""
    def __init__(self, slot: str, limiar: float = 0.5):
        self.slot = slot
        self.limiar = limiar
        self.nome = f"slot_{slot}"

    def bate(self, gold, pred) -> bool:
        return LexicalMatcher._overlap(getattr(gold, self.slot), getattr(pred, self.slot)) > self.limiar


def avaliar_por_campo(caminho_gold: str, caminho_pred: str, limiar: float = 0.5) -> Dict[str, Contadores]:
    """Um Contadores por campo (arg1, rel, arg2) + 'tripla_completa' (referência)."""
    golds = RobustJSONLReader(Path(caminho_gold)).carregar().objetos
    preds = achatar_predicoes(RobustJSONLReader(Path(caminho_pred)).carregar().objetos)

    gold_por_sentenca = {
        _normalizar_sentenca(g.get("sentence", "") if isinstance(g, dict) else ""): g
        for g in golds
    }

    # um matcher por slot + o matcher de tripla completa (os 3 slots juntos)
    matchers: Dict[str, TripleMatcher] = {campo: SlotMatcher(campo, limiar) for campo in CAMPOS}
    matchers["tripla_completa"] = LexicalMatcher(limiar=limiar)

    contadores = {k: Contadores() for k in matchers}

    # casa por frase e conta VP/FP/FN de cada campo separadamente
    sentencas_pred = set()
    for item_pred in preds:
        if not isinstance(item_pred, dict):
            continue
        chave = _normalizar_sentenca(item_pred.get("sentence", ""))
        sentencas_pred.add(chave)
        item_gold = gold_por_sentenca.get(chave)
        if item_gold is None:
            continue
        g_tri = extrair_triplas(item_gold)
        p_tri = extrair_triplas(item_pred)
        for nome, matcher in matchers.items():
            c = comparar_triplas(g_tri, p_tri, matcher)
            contadores[nome].vp += c.vp
            contadores[nome].fp += c.fp
            contadores[nome].fn += c.fn

    # frases do gold nunca cobertas -> penaliza o recall (igual ao resultados.py)
    for chave, item_gold in gold_por_sentenca.items():
        if chave in sentencas_pred:
            continue
        n = len(extrair_triplas(item_gold))
        for nome in matchers:
            contadores[nome].fn += n

    return contadores


def descobrir_pastas(raiz_respostas, lotes_filtro):
    raiz = Path(raiz_respostas)
    for lote in sorted(raiz.glob("*_batches")):
        if lotes_filtro and lote.name != f"{lotes_filtro}_batches":
            continue
        for pasta in sorted(lote.glob("Respostas *")):
            yield lote.name, pasta

def plotar_por_campo(linhas, titulo, caminho_base):
    """Barras agrupadas: por modelo, um grupo com o F1 de arg1/rel/arg2."""
    dados, modelos = {}, []
    for l in linhas:
        if l["campo"] == "tripla_completa":      # a referência não vai pro gráfico
            continue
        dados.setdefault(l["modelo"], {})[l["campo"]] = l["f1"]
        if l["modelo"] not in modelos:
            modelos.append(l["modelo"])
    modelos.sort(key=lambda m: -sum(dados[m].values()))   # melhor média primeiro

    x = np.arange(len(modelos))
    w = 0.26
    fig, ax = plt.subplots(figsize=(max(7, len(modelos) * 1.5), 4.5))
    for i, campo in enumerate(CAMPOS):                     # arg1, rel, arg2 (ordem fixa)
        vals = [dados[m].get(campo, 0.0) for m in modelos]
        barras = ax.bar(x + (i - 1) * w, vals, w, label=campo,
                        color=CORES_CAMPO[campo], edgecolor="white", linewidth=0.5)
        ax.bar_label(barras, fmt="%.2f", fontsize=7, padding=2, color="#444")  # rótulo direto

    ax.set_xticks(x)
    ax.set_xticklabels([m.replace("respostas_", "").replace("resposta", "") for m in modelos],
                       rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("F1 (lexical)")
    ax.set_ylim(0, 1)
    ax.set_title(titulo, fontsize=11)
    ax.legend(title="campo", frameon=False, fontsize=8)    # legenda p/ 3 séries
    ax.spines[["top", "right"]].set_visible(False)         # eixos recessivos
    ax.grid(axis="y", color="#e6e6e6", linewidth=0.6)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(f"{caminho_base}.png", dpi=150, bbox_inches="tight")
    fig.savefig(f"{caminho_base}.pdf", bbox_inches="tight")   # PDF p/ o artigo
    plt.close(fig)

def main():
    parser = argparse.ArgumentParser(description="Avaliação OIE por campo (arg1/rel/arg2)")
    parser.add_argument("--corpus", default=CORPUS_PADRAO, choices=list(CORPORA),
                        help="Corpus (define gold + pastas). Default: %(default)s")
    parser.add_argument("--lotes", default=None, help="Filtra um tamanho de lote (ex.: 10)")
    parser.add_argument("--gold", default=None, help="Gold. Sobrepõe o gold do corpus.")
    parser.add_argument("--limiar", type=float, default=0.5)
    args = parser.parse_args()

    cfg = resolver_corpus(args.corpus)
    gold = args.gold or cfg["gold"]

    for lote_nome, pasta in descobrir_pastas(cfg["respostas"], args.lotes):
        print(f"=== {lote_nome}/{pasta.name} ===")
        linhas = []
        for arq in sorted(pasta.glob("*.jsonl")):
            conts = avaliar_por_campo(gold, str(arq), args.limiar)
            for campo, c in conts.items():
                linhas.append({
                    "modelo": arq.stem, "campo": campo,
                    "precisao": round(c.precisao(), 4),
                    "recall": round(c.recall(), 4),
                    "f1": round(c.f1(), 4),
                    "vp": c.vp, "fp": c.fp, "fn": c.fn,
                })
        for l in linhas:
            print(f"  {l['modelo']:<24} {l['campo']:<16} P={l['precisao']:.3f} R={l['recall']:.3f} F1={l['f1']:.3f}")

        saida_dir = cfg["saida"] / lote_nome
        saida_dir.mkdir(parents=True, exist_ok=True)
        saida = saida_dir / f"resultados_por_campo_{pasta.name.replace(' ', '_')}.csv"
        with open(saida, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["modelo", "campo", "precisao", "recall", "f1", "vp", "fp", "fn"])
            w.writeheader()
            w.writerows(linhas)
        print(f"  -> salvo em {saida}\n")
        plotar_por_campo(
                    linhas,
                    f"F1 por campo — {pasta.name}",
                    str(saida_dir / f"grafico_por_campo_{pasta.name.replace(' ', '_')}"),
                )
        print(f"  -> gráfico salvo em {saida_dir}/grafico_por_campo_...png/.pdf")
        

   

if __name__ == "__main__":
    main()