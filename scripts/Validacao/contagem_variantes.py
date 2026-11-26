#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
contagem_variantes.py
======================

Conta, para o gold e para cada resposta, quantos PARES DE VARIANTES existem.

DEFINIÇÃO. Duas triplas da MESMA sentença formam um par de variantes quando:
  1. os tokens de arg1 de uma estão contidos nos da outra (ou são iguais),
  2. as relações compartilham pelo menos um token, e
  3. os tokens de arg2 de uma estão contidos nos da outra, sem serem iguais (um é versão mais curta do outro).
Exemplo: ("A postura do RSPB", "o colocou em", "conflito") e
         ("A postura do RSPB", "o colocou em", "conflito com muitos líderes conservadores").

POR QUE IMPORTA. O gold tem muitas proposições escritas em mais de um comprimento de argumento, e o avaliador casa
1 para 1. Um prompt que faz o modelo gerar variantes consegue casar com várias triplas do gold e sobe o F1. Esta
contagem mede quanto cada prompt induz esse comportamento.

LIMITES. Compara tokens por conjunto (sem ordem, sem lematização), então é uma aproximação. Conta pares, não
triplas: uma proposição com 3 comprimentos gera 3 pares.

USO (da raiz do repositório)
    python scripts/Validacao/contagem_variantes.py --corpus bia oiec_pt
Saída: Outputs/analise_regras/<corpus>/variantes_<lotes>_batches.csv
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bootstrap_ic import carregar_gold  # noqa: E402
from resultados import CORPORA, RobustJSONLReader, _normalizar_sentenca as N, achatar_predicoes, extrair_triplas  # noqa: E402

logging.disable(logging.CRITICAL)
RAIZ = Path(__file__).resolve().parents[2]


def toks(s: str) -> set:
    return set(s.lower().split())


def pares_variantes(trs) -> int:
    n = 0
    for i in range(len(trs)):
        for j in range(i + 1, len(trs)):
            a, b = trs[i], trs[j]
            a1, b1 = toks(a.arg1), toks(b.arg1)
            if not (a1 <= b1 or b1 <= a1):
                continue
            if not (toks(a.rel) & toks(b.rel)):
                continue
            x, y = toks(a.arg2), toks(b.arg2)
            if x and y and x != y and (x <= y or y <= x):
                n += 1
    return n


def canon(modelo: str) -> str:
    return re.sub(r"^respostas?_?", "", modelo)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", nargs="*", default=["bia", "oiec_pt"])
    ap.add_argument("--lotes", type=int, default=10)
    a = ap.parse_args()
    for c in a.corpus:
        cfg = CORPORA[c]
        chaves, gold = carregar_gold(RAIZ / cfg["gold"])
        n_gold = sum(len(gold[k]) for k in chaves)
        linhas = [{"corpus": c, "pasta": "GOLD", "modelo": "gold", "llm": "gold", "n_triplas": n_gold,
                   "pares_variantes": sum(pares_variantes(gold[k]) for k in chaves)}]
        base = RAIZ / cfg["respostas"] / f"{a.lotes}_batches"
        for pasta in sorted(p for p in base.glob("Respostas*") if p.is_dir()):
            nome_pasta = pasta.name.replace("Respostas ", "")
            for arq in sorted(pasta.glob("*.jsonl")):
                objs = achatar_predicoes(RobustJSONLReader(arq).carregar().objetos)
                por = {}
                for o in objs:
                    if isinstance(o, dict):
                        k = N(o.get("sentence", ""))
                        if k in gold:                       # só sentenças do gold, como o avaliador
                            por.setdefault(k, extrair_triplas(o))
                n_tr = sum(len(v) for v in por.values())
                linhas.append({"corpus": c, "pasta": nome_pasta, "modelo": arq.stem, "llm": canon(arq.stem),
                               "n_triplas": n_tr, "pares_variantes": sum(pares_variantes(v) for v in por.values())})
        df = pd.DataFrame(linhas)
        df["pares_por_100_triplas"] = (100 * df["pares_variantes"] / df["n_triplas"].where(df["n_triplas"] > 0)).round(1)
        saida = RAIZ / "Outputs" / "analise_regras" / c
        saida.mkdir(parents=True, exist_ok=True)
        df.to_csv(saida / f"variantes_{a.lotes}_batches.csv", index=False)
        pd.set_option("display.width", 200)
        print(f"\n=== {c} ===")
        print(df.sort_values(["pasta", "llm"]).to_string(index=False))
        print("saída:", saida)


if __name__ == "__main__":
    main()
