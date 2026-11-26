#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
caracterizar_corpus.py
=======================

Descreve o GOLD de cada corpus com medidas que ajudam a explicar os resultados dos sistemas.

MEDIDAS (todas calculadas sobre o gold)
  n_sentencas, n_triplas, triplas_por_sentenca     volume: quanto o gold espera extrair de cada sentença
  pct_sentencas_sem_tripla                         sentenças que o gold deixa sem nenhuma tripla
  palavras_por_sentenca                            tamanho médio da sentença
  palavras_arg1 / palavras_rel / palavras_arg2     tamanho médio de cada campo (em palavras)
  pct_triplas_arg_so_pronome                       triplas em que arg1 ou arg2 é formado só por pronome
  pct_relacao_copular                              relação "é", "são", "foi"... (tripla de identidade ou atributo)
  pares_variantes_por_100_triplas                  mesma relação escrita em mais de um tamanho de argumento
                                                   (definição em contagem_variantes.py)
  pct_triplas_contracao_separada                   preposição e artigo separados, como "de o" no lugar de "do"

LIMITES. São medidas descritivas do gold, não prova de causa. A detecção de contração separada usa uma lista de
pares preposição + artigo que não existem escritos assim em português (de o, em a, por os...).

FALSOS POSITIVOS EM SENTENÇAS VAZIAS. Para cada resposta, quantos falsos positivos caem em sentenças que o gold deixa sem
nenhuma tripla (qualquer tripla gerada ali é falso positivo por definição). Saída: fp_sentencas_vazias_<lotes>_batches.csv

USO (da raiz do repositório)
    python scripts/Validacao/caracterizar_corpus.py
    python scripts/Validacao/caracterizar_corpus.py --corpus bia oiec_pt oiec_pt_abs
Saída: Outputs/analise_regras/<corpus>/caracteristicas_corpus.csv
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analise_pronomes_transitividade import so_pronome  # noqa: E402
from contagem_variantes import pares_variantes  # noqa: E402
from bootstrap_ic import canon, carregar_gold, contadores_por_sentenca  # noqa: E402
from resultados import CORPORA, LexicalMatcher, RobustJSONLReader, achatar_predicoes, extrair_triplas  # noqa: E402

logging.disable(logging.CRITICAL)
RAIZ = Path(__file__).resolve().parents[2]

COPULARES = {"é", "são", "era", "eram", "foi", "foram", "ser", "está", "estão", "estava", "estavam"}
# pares que em português corrente se escrevem contraídos (do, da, no, na, ao, pelo...), logo só aparecem separados
# quando o anotador separou a contração
CONTRACAO_SEPARADA = re.compile(r"\b(de|em|por)\s+(o|a|os|as)\b|\ba\s+(o|os|as)\b", re.IGNORECASE)


def nw(s: str) -> int:
    return len(str(s).split())


def caracterizar(corpus: str) -> dict:
    cfg = CORPORA[corpus]
    objs = [o for o in achatar_predicoes(RobustJSONLReader(RAIZ / cfg["gold"]).carregar().objetos) if isinstance(o, dict)]
    n_sent = len(objs)
    por_sent = [extrair_triplas(o) for o in objs]
    trs = [t for lst in por_sent for t in lst]
    n_tr = len(trs)
    cop = sum(1 for t in trs if t.rel.strip().lower() in COPULARES)
    pron = sum(1 for t in trs if so_pronome(t.arg1) or so_pronome(t.arg2))
    contr = sum(1 for t in trs if CONTRACAO_SEPARADA.search(f"{t.arg1} {t.rel} {t.arg2}"))
    sem = sum(1 for lst in por_sent if not lst)
    return {
        "corpus": corpus,
        "n_sentencas": n_sent,
        "n_triplas": n_tr,
        "triplas_por_sentenca": round(n_tr / n_sent, 2),
        "pct_sentencas_sem_tripla": round(sem / n_sent, 3),
        "palavras_por_sentenca": round(sum(nw(o.get("sentence", "")) for o in objs) / n_sent, 1),
        "palavras_arg1": round(sum(nw(t.arg1) for t in trs) / n_tr, 2),
        "palavras_rel": round(sum(nw(t.rel) for t in trs) / n_tr, 2),
        "palavras_arg2": round(sum(nw(t.arg2) for t in trs) / n_tr, 2),
        "pct_triplas_arg_so_pronome": round(pron / n_tr, 3),
        "pct_relacao_copular": round(cop / n_tr, 3),
        "pares_variantes_por_100_triplas": round(100 * sum(pares_variantes(lst) for lst in por_sent) / n_tr, 1),
        "pct_triplas_contracao_separada": round(contr / n_tr, 3),
    }


def fp_em_vazias(corpus: str, lotes: int) -> pd.DataFrame:
    cfg = CORPORA[corpus]
    chaves, gold = carregar_gold(str(RAIZ / cfg["gold"]))
    vazia = [len(gold[k]) == 0 for k in chaves]
    if not any(vazia):
        return pd.DataFrame()
    matcher = LexicalMatcher(0.5)
    linhas = []
    base = RAIZ / cfg["respostas"] / f"{lotes}_batches"
    for pasta in sorted(p for p in base.glob("Respostas*") if p.is_dir()):
        for arq in sorted(pasta.glob("*.jsonl")):
            m = contadores_por_sentenca(chaves, gold, arq, matcher)
            fp, fp_v = int(m[:, 1].sum()), int(m[vazia, 1].sum())
            linhas.append({"corpus": corpus, "pasta": pasta.name.replace("Respostas ", ""), "modelo": arq.stem,
                           "llm": canon(arq.stem), "n_fp": fp, "n_fp_em_sentencas_vazias": fp_v,
                           "pct_fp_em_sentencas_vazias": round(fp_v / fp, 3) if fp else 0.0})
    return pd.DataFrame(linhas)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", nargs="*", default=["bia", "oiec_pt", "oiec_pt_abs"])
    ap.add_argument("--lotes", type=int, default=10)
    a = ap.parse_args()
    linhas = []
    for c in a.corpus:
        d = caracterizar(c)
        linhas.append(d)
        saida = RAIZ / "Outputs" / "analise_regras" / c
        saida.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([d]).to_csv(saida / "caracteristicas_corpus.csv", index=False)
        fv = fp_em_vazias(c, a.lotes)
        if len(fv):
            fv.to_csv(saida / f"fp_sentencas_vazias_{a.lotes}_batches.csv", index=False)
    pd.set_option("display.width", 220, "display.max_columns", 30)
    print(pd.DataFrame(linhas).set_index("corpus").T.to_string())


if __name__ == "__main__":
    main()
