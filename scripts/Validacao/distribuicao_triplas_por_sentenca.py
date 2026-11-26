#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
distribuicao_triplas_por_sentenca.py
=====================================

Para o gold e para cada resposta, quantas sentenças têm 0, 1, 2 ou 3 ou mais triplas. Mostra o PERFIL de extração: um sistema que
extrai uma tripla principal por sentença tem um perfil muito diferente de um que extrai de duas a quatro, mesmo com F1 parecido.

Colunas: pct_sem_tripla, pct_1_tripla, pct_2_triplas, pct_3_ou_mais (frações de 0 a 1, sobre as sentenças do gold) e
triplas_por_sentenca (média). A linha GOLD é a referência.

USO (da raiz do repositório)
    python scripts/Validacao/distribuicao_triplas_por_sentenca.py --corpus bia oiec_pt
Saída: Outputs/analise_regras/<corpus>/distribuicao_triplas_<lotes>_batches.csv
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


def canon(m: str) -> str:
    return re.sub(r"^respostas?_?", "", m)


def linha(corpus, pasta, modelo, contagens) -> dict:
    n = len(contagens)
    return {"corpus": corpus, "pasta": pasta, "modelo": modelo, "llm": canon(modelo), "n_sentencas": n,
            "pct_sem_tripla": round(sum(1 for c in contagens if c == 0) / n, 3),
            "pct_1_tripla": round(sum(1 for c in contagens if c == 1) / n, 3),
            "pct_2_triplas": round(sum(1 for c in contagens if c == 2) / n, 3),
            "pct_3_ou_mais": round(sum(1 for c in contagens if c >= 3) / n, 3),
            "triplas_por_sentenca": round(sum(contagens) / n, 2)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", nargs="*", default=["bia", "oiec_pt", "oiec_pt_abs"])
    ap.add_argument("--lotes", type=int, default=10)
    a = ap.parse_args()
    for c in a.corpus:
        cfg = CORPORA[c]
        chaves, gold = carregar_gold(str(RAIZ / cfg["gold"]))
        linhas = [linha(c, "GOLD", "gold", [len(gold[k]) for k in chaves])]
        base = RAIZ / cfg["respostas"] / f"{a.lotes}_batches"
        for pasta in sorted(p for p in base.glob("Respostas*") if p.is_dir()):
            for arq in sorted(pasta.glob("*.jsonl")):
                por = {}
                for o in achatar_predicoes(RobustJSONLReader(arq).carregar().objetos):
                    if isinstance(o, dict):
                        k = N(o.get("sentence", ""))
                        if k not in por:
                            por[k] = len(extrair_triplas(o))
                linhas.append(linha(c, pasta.name.replace("Respostas ", ""), arq.stem, [por.get(k, 0) for k in chaves]))
        saida = RAIZ / "Outputs" / "analise_regras" / c
        saida.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame(linhas)
        df.to_csv(saida / f"distribuicao_triplas_{a.lotes}_batches.csv", index=False)
        print(f"\n=== {c} ===")
        print(df[["pasta", "llm", "pct_sem_tripla", "pct_1_tripla", "pct_2_triplas", "pct_3_ou_mais", "triplas_por_sentenca"]]
              .sort_values(["pasta", "llm"]).to_string(index=False))


if __name__ == "__main__":
    main()
