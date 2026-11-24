#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bootstrap_ic.py
================

Intervalos de confiança (bootstrap por SENTENÇA) para o F1 de cada sistema/LLM, e diferenças pareadas entre
sistemas. Serve para dizer quais diferenças do ranking são distinguíveis do acaso com poucas sentenças
(100 no oiec_pt, 262 na bia).

COMO FUNCIONA
  1. Para cada sistema, calcula por sentença os contadores vp/fp/fn com o MESMO casamento do `resultados.py`
     (LexicalMatcher com limiar 0,5 e ExactMatcher, casamento guloso 1 para 1).
  2. Sorteia B vezes N sentenças COM reposição (as mesmas sentenças sorteadas valem para todos os sistemas,
     por isso as diferenças entre sistemas são PAREADAS) e recalcula o F1 somando os contadores.
  3. Reporta o F1 (valor observado), o intervalo de 95% (percentis 2,5 e 97,5) e, para as diferenças,
     o intervalo da diferença e se ele exclui o zero.

  F1 = 2*VP / (2*VP + FP + FN), idêntico ao F1 de precisão e recall calculado pelo `resultados.py`.

COMPARAÇÕES
  - ic_<metrica>.csv                      F1 e IC de todos os sistemas, ordenado.
  - diferencas_vs_lider_<metrica>.csv     cada sistema contra o de maior F1 do corpus.
  - prompt_vs_semregras_<metrica>.csv     o MESMO LLM com cada prompt de regras contra o prompt sem regras.

LIMITES
  - O bootstrap por sentença trata as sentenças como amostra de uma população maior. Com 100 sentenças os
    intervalos são largos. "Intervalo inclui zero" quer dizer "não distinguível aqui", não "são iguais".
  - Uma coleta, um prompt, uma execução por LLM. Não mede variação entre execuções do mesmo modelo.
  - Muitas comparações ao mesmo tempo aumentam a chance de um intervalo excluir zero por acaso.

USO (da raiz do repositório)
    python scripts/Validacao/bootstrap_ic.py                         # os 3 corpora, lote 10, B=5000
    python scripts/Validacao/bootstrap_ic.py --corpus oiec_pt --B 10000
Saída: Outputs/bootstrap/<corpus>/
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from resultados import (  # noqa: E402
    CORPORA, ExactMatcher, LexicalMatcher, RobustJSONLReader, _normalizar_sentenca, achatar_predicoes,
    comparar_triplas, extrair_triplas,
)

logging.disable(logging.CRITICAL)      # o RobustJSONLReader/avaliador é verboso; aqui só interessa o resultado


def canon(modelo: str) -> str:
    """respostaGrok4.0Fast / respostas_gpt5.5_mini / respostasGemini3.1Pro -> nome sem o prefixo."""
    return re.sub(r"^respostas?_?", "", modelo)


def carregar_gold(caminho: str):
    objs = achatar_predicoes(RobustJSONLReader(Path(caminho)).carregar().objetos)
    chaves, triplas = [], {}
    for o in objs:
        if isinstance(o, dict):
            k = _normalizar_sentenca(o.get("sentence", ""))
            chaves.append(k)
            triplas[k] = extrair_triplas(o)
    return chaves, triplas


def contadores_por_sentenca(chaves, gold, arquivo: Path, matcher) -> np.ndarray:
    """Matriz (n_sentenças, 3) com vp, fp, fn por sentença do gold, espelhando o avaliador."""
    pos = {k: i for i, k in enumerate(chaves)}
    m = np.zeros((len(chaves), 3), dtype=np.int64)
    cobertas = set()
    objs = achatar_predicoes(RobustJSONLReader(arquivo).carregar().objetos)
    for item in objs:
        if not isinstance(item, dict):
            continue
        k = _normalizar_sentenca(item.get("sentence", ""))
        if k not in pos:
            continue                       # sentença que não existe no gold: o avaliador ignora
        cobertas.add(k)
        c = comparar_triplas(gold[k], extrair_triplas(item), matcher)
        m[pos[k]] += (c.vp, c.fp, c.fn)
    for k in chaves:
        if k not in cobertas:
            m[pos[k], 2] += len(gold[k])   # gold sem nenhuma resposta: penaliza o recall
    return m


def f1_de(soma: np.ndarray) -> np.ndarray:
    vp, fp, fn = soma[..., 0], soma[..., 1], soma[..., 2]
    den = 2 * vp + fp + fn
    return np.where(den > 0, 2 * vp / np.maximum(den, 1), 0.0)


def ic(x: np.ndarray, nivel: float = 95.0):
    a = (100 - nivel) / 2
    return float(np.percentile(x, a)), float(np.percentile(x, 100 - a))


def processar_corpus(corpus: str, lotes: int, B: int, seed: int, metrica: str, saida_raiz: Path) -> None:
    cfg = CORPORA[corpus]
    matcher = LexicalMatcher(0.5) if metrica == "lexical" else ExactMatcher()
    chaves, gold = carregar_gold(cfg["gold"])
    n = len(chaves)
    base = Path(cfg["respostas"]) / f"{lotes}_batches"

    sistemas: Dict[str, np.ndarray] = {}
    meta: Dict[str, dict] = {}
    for pasta in sorted(p for p in base.glob("Respostas*") if p.is_dir()):
        for arq in sorted(pasta.glob("*.jsonl")):
            nome = f"{pasta.name.replace('Respostas ', '')}|{arq.stem}"
            sistemas[nome] = contadores_por_sentenca(chaves, gold, arq, matcher)
            meta[nome] = {"pasta": pasta.name.replace("Respostas ", ""), "modelo": arq.stem, "canon": canon(arq.stem)}
    if not sistemas:
        print(f"[{corpus}] nenhuma resposta em {base}")
        return

    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(B, n))                      # as MESMAS sentenças para todos os sistemas
    boot_f1 = {k: f1_de(m[idx].sum(axis=1)) for k, m in sistemas.items()}   # (B,)
    obs_f1 = {k: float(f1_de(m.sum(axis=0))) for k, m in sistemas.items()}

    linhas = []
    for k in sistemas:
        lo, hi = ic(boot_f1[k])
        linhas.append({"corpus": corpus, **meta[k], "n_sentencas": n, "f1": round(obs_f1[k], 3),
                       "ic95_inf": round(lo, 3), "ic95_sup": round(hi, 3), "largura": round(hi - lo, 3)})
    df = pd.DataFrame(linhas).sort_values("f1", ascending=False).reset_index(drop=True)

    # ---- confere o F1 observado com o CSV do resultados.py (avisa se o CSV estiver desatualizado)
    avisos = []
    for _, r in df.iterrows():
        csv = Path(cfg["saida"]) / f"{lotes}_batches" / f"resultados_Respostas_{r['pasta']}.csv"
        if csv.exists():
            d = pd.read_csv(csv)
            col = "f1_lexical" if metrica == "lexical" else "f1_exact"
            achou = d[d["modelo"] == r["modelo"]]
            if len(achou) and abs(float(achou[col].iloc[0]) - r["f1"]) > 0.002:
                avisos.append(f"{r['pasta']}|{r['modelo']}: bootstrap {r['f1']:.3f} x CSV {float(achou[col].iloc[0]):.3f}")

    # ---- diferenças pareadas contra o líder
    lider = df.iloc[0]
    kl = f"{lider['pasta']}|{lider['modelo']}"
    dif = []
    for k in sistemas:
        if k == kl:
            continue
        d = boot_f1[k] - boot_f1[kl]
        lo, hi = ic(d)
        dif.append({"corpus": corpus, **meta[k], "f1": round(obs_f1[k], 3), "lider": kl,
                    "dif_vs_lider": round(obs_f1[k] - obs_f1[kl], 3), "ic95_inf": round(lo, 3), "ic95_sup": round(hi, 3),
                    "distinguivel_do_lider": bool(hi < 0 or lo > 0)})
    dif = pd.DataFrame(dif).sort_values("dif_vs_lider", ascending=False)

    # ---- mesmo LLM: cada prompt de regras contra SemRegras
    pv = []
    por_llm: Dict[str, Dict[str, str]] = {}
    for k, m in meta.items():
        por_llm.setdefault(m["canon"], {})[m["pasta"]] = k
    for llm, pastas in por_llm.items():
        ref = pastas.get("SemRegras")
        if not ref:
            continue
        for pasta, k in pastas.items():
            if pasta == "SemRegras":
                continue
            d = boot_f1[k] - boot_f1[ref]
            lo, hi = ic(d)
            pv.append({"corpus": corpus, "llm": llm, "prompt": pasta, "f1_prompt": round(obs_f1[k], 3),
                       "f1_semregras": round(obs_f1[ref], 3), "dif": round(obs_f1[k] - obs_f1[ref], 3),
                       "ic95_inf": round(lo, 3), "ic95_sup": round(hi, 3), "distinguivel": bool(hi < 0 or lo > 0)})
    pv = pd.DataFrame(pv)

    saida = saida_raiz / corpus
    saida.mkdir(parents=True, exist_ok=True)
    df.to_csv(saida / f"ic_{metrica}.csv", index=False)
    dif.to_csv(saida / f"diferencas_vs_lider_{metrica}.csv", index=False)
    pv.to_csv(saida / f"prompt_vs_semregras_{metrica}.csv", index=False)

    pd.set_option("display.width", 220, "display.max_columns", 20, "display.max_rows", 200)
    print(f"\n{'=' * 100}\n{corpus}: F1 {metrica}, {n} sentenças, B={B}, semente {seed}\n{'=' * 100}")
    print(df[["pasta", "modelo", "f1", "ic95_inf", "ic95_sup", "largura"]].to_string(index=False))
    print(f"\nLíder: {kl}. Sistemas NÃO distinguíveis do líder (IC da diferença inclui 0):")
    nd = dif[~dif["distinguivel_do_lider"]]
    print(nd[["pasta", "modelo", "f1", "dif_vs_lider", "ic95_inf", "ic95_sup"]].to_string(index=False) if len(nd) else "  nenhum")
    if len(pv):
        print("\nMesmo LLM, prompt de regras contra SemRegras:")
        print(pv[["llm", "prompt", "f1_prompt", "f1_semregras", "dif", "ic95_inf", "ic95_sup", "distinguivel"]].to_string(index=False))
    if avisos:
        print("\nAVISO: F1 do bootstrap difere do CSV do resultados.py (CSV desatualizado ou duplicatas):")
        for a in avisos:
            print("  ", a)
    print("\nCSVs em", saida)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", nargs="*", default=["bia", "oiec_pt", "oiec_pt_abs"])
    ap.add_argument("--lotes", type=int, default=10)
    ap.add_argument("--B", type=int, default=5000, help="número de reamostragens (padrão 5000)")
    ap.add_argument("--semente", type=int, default=42)
    ap.add_argument("--metrica", choices=["lexical", "exact"], default="lexical")
    ap.add_argument("--saida", default="Outputs/bootstrap")
    a = ap.parse_args()
    for c in a.corpus:
        processar_corpus(c, a.lotes, a.B, a.semente, a.metrica, Path(a.saida))


if __name__ == "__main__":
    main()
