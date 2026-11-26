#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
concordancia_entre_sistemas.py
===============================

Matriz de concordância entre sistemas, incluindo os extratores que não são LLMs e o gold.

DEFINIÇÃO. Para dois sistemas A (linha) e B (coluna), a célula é a porcentagem das triplas de A que B também tem, isto é,
triplas de B na MESMA sentença que casam com a de A pelo critério lexical do avaliador (sobreposição de tokens maior que 0,5
em arg1, rel e arg2). A matriz não é simétrica, porque A e B podem ter números de triplas diferentes.
Quando B é o gold, a célula lembra a precisão de A. Quando A é o gold, lembra o recall de B. A diferença é que aqui o
casamento NÃO é 1 para 1: uma tripla do outro sistema pode ser usada por várias triplas de A.

SISTEMAS. Os LLMs entram com um único prompt (padrão: SemRegras, que todos os LLMs têm completo nos dois corpora), os
extratores locais vêm da pasta SistemasExtrativos, e o gold é a última linha e coluna.

LIMITES. Concordância não é correção: sistemas parecidos concordam mesmo errando. Com um único prompt por LLM, a matriz não
mostra o efeito do prompt.

USO (da raiz do repositório)
    python scripts/Validacao/concordancia_entre_sistemas.py --corpus bia oiec_pt
    python scripts/Validacao/concordancia_entre_sistemas.py --prompt ExtrativoOIEC-PT
Saída: Outputs/analise_regras/<corpus>/concordancia_sistemas.csv (formato longo: corpus, a, b, pct, n_triplas_a)
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
from resultados import (CORPORA, LexicalMatcher, RobustJSONLReader, _normalizar_sentenca as N,  # noqa: E402
                        achatar_predicoes, extrair_triplas)

logging.disable(logging.CRITICAL)
RAIZ = Path(__file__).resolve().parents[2]


def canon(m: str) -> str:
    return re.sub(r"^respostas?_?", "", m)


def triplas_por_sentenca(arq: Path, chaves: set) -> dict:
    out = {}
    for o in achatar_predicoes(RobustJSONLReader(arq).carregar().objetos):
        if isinstance(o, dict):
            k = N(o.get("sentence", ""))
            if k in chaves and k not in out:
                out[k] = extrair_triplas(o)
    return out


PROMPTS_AGREGADO = ["SemRegras", "ExtrativoDPTO-IE", "ExtrativoOIEC-PT", "ExtrativoPTOIE-DP", "ExtrativoBIA-completo"]
LLMS_AGREGADO = ["Claude_Sonnet5", "GeminiHydrogen4", "Grok4.0Fast", "gpt5.5_mini"]


def agregado_llm_locais(corpus: str, lotes: int, m: LexicalMatcher) -> pd.DataFrame:
    """Para cada LLM, % das suas triplas (somadas sobre os 5 prompts) que cada extrator local e o gold também têm.
    Diferente da matriz acima, que usa um único prompt, este valor não depende de um prompt específico."""
    cfg = CORPORA[corpus]
    chaves, gold = carregar_gold(str(RAIZ / cfg["gold"]))
    ks = set(chaves)
    base = RAIZ / cfg["respostas"] / f"{lotes}_batches"
    alvos = {canon(arq.stem): triplas_por_sentenca(arq, ks) for arq in sorted((base / "Respostas SistemasExtrativos").glob("*.jsonl"))}
    alvos["Gold"] = {k: gold[k] for k in chaves}
    acertos = {(l, b): 0 for l in LLMS_AGREGADO for b in alvos}
    total = {l: 0 for l in LLMS_AGREGADO}
    for prompt in PROMPTS_AGREGADO:
        for arq in sorted((base / f"Respostas {prompt}").glob("*.jsonl")):
            llm = canon(arq.stem)
            if llm not in LLMS_AGREGADO:
                continue
            da = triplas_por_sentenca(arq, ks)
            total[llm] += sum(len(v) for v in da.values())
            for nb, db in alvos.items():
                for k, tr_a in da.items():
                    tr_b = db.get(k, [])
                    acertos[(llm, nb)] += sum(1 for ta in tr_a if any(m.bate(tb, ta) for tb in tr_b))
    linhas = [{"corpus": corpus, "llm": l, "b": b, "pct": round(acertos[(l, b)] / total[l], 4) if total[l] else 0.0, "n_triplas_a": total[l]}
              for l in LLMS_AGREGADO for b in alvos]
    return pd.DataFrame(linhas)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", nargs="*", default=["bia", "oiec_pt"])
    ap.add_argument("--lotes", type=int, default=10)
    ap.add_argument("--prompt", default="SemRegras", help="pasta de prompt (sem o prefixo 'Respostas ') usada para os LLMs")
    a = ap.parse_args()
    m = LexicalMatcher(0.5)
    for c in a.corpus:
        cfg = CORPORA[c]
        chaves, gold = carregar_gold(str(RAIZ / cfg["gold"]))
        ks = set(chaves)
        base = RAIZ / cfg["respostas"] / f"{a.lotes}_batches"
        sist = {}
        for pasta in (f"Respostas {a.prompt}", "Respostas SistemasExtrativos"):
            for arq in sorted((base / pasta).glob("*.jsonl")):
                sist[canon(arq.stem)] = triplas_por_sentenca(arq, ks)
        sist["Gold"] = {k: gold[k] for k in chaves}
        linhas = []
        for na, da in sist.items():
            n_a = sum(len(v) for v in da.values())
            for nb, db in sist.items():
                if na == nb:
                    continue
                ach = 0
                for k, tr_a in da.items():
                    tr_b = db.get(k, [])
                    for ta in tr_a:
                        if any(m.bate(tb, ta) for tb in tr_b):
                            ach += 1
                linhas.append({"corpus": c, "a": na, "b": nb, "pct": round(ach / n_a, 4) if n_a else 0.0, "n_triplas_a": n_a})
        df = pd.DataFrame(linhas)
        saida = RAIZ / "Outputs" / "analise_regras" / c
        saida.mkdir(parents=True, exist_ok=True)
        df.to_csv(saida / "concordancia_sistemas.csv", index=False)
        ag = agregado_llm_locais(c, a.lotes, m)
        ag.to_csv(saida / "concordancia_llm_agregada.csv", index=False)
        print(f"\n--- {c}: LLMs (somando os 5 prompts) x extratores locais e gold ---")
        print((ag.pivot(index="llm", columns="b", values="pct") * 100).round(0).to_string())
        pd.set_option("display.width", 250, "display.max_columns", 20)
        print(f"\n=== {c} (LLMs com {a.prompt}) ===")
        print((df.pivot(index="a", columns="b", values="pct") * 100).round(0).to_string())
        print("saída:", saida)


if __name__ == "__main__":
    main()
