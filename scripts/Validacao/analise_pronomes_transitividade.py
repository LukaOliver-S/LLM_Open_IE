#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analise_pronomes_transitividade.py
===================================

Testa duas contradições entre catálogos de regras (ver `catalogo de regras.xlsx`):

  1. PRONOME COMO ARGUMENTO
     BIA (B01, B10): argumento formado só por pronome é inválido.
     OIEC-PT (E5):   o núcleo do argumento pode ser pronome.
  2. TRANSITIVIDADE
     OIEC-PT (S5):   não validar fatos obtidos por inferência como a transitividade.
     DptOIE (D09) e DptOIE-PY (P17): geram (B, R, C) a partir de (A, é, B) e (A, R, C).

Para cada corpus e cada sistema/LLM, reporta:
  - quantas triplas têm argumento só de pronome (e a precisão delas contra o restante);
  - quantas triplas seguem o padrão de transitividade (e a precisão delas contra o restante);
  - o F1 lexical original e o F1 lexical SEM essas triplas ("e se o sistema não as gerasse?").
No gold, só conta quantas triplas têm esses padrões (o gold só tem triplas válidas).

HEURÍSTICAS (limites)
  - "Só pronome": todos os tokens do argumento estão na lista PRONOMES abaixo (pessoais, demonstrativos,
    relativos, e contrações como "dele", "disso"). Pronomes indefinidos ("todos") não entram.
  - "Transitividade": numa mesma sentença existem (A, REL_COP, B) e (A, R, C), e a tripla (B, R, C) também
    existe, com B diferente de A. REL_COP = {é, são, foi, era, eram}. É uma aproximação do mecanismo do DptOIE,
    não a detecção exata das regras D09/P17.
  - O casamento com o gold usa o MESMO critério do `resultados.py` (LexicalMatcher, limiar 0,5, guloso 1 para 1).

USO (da raiz do repositório)
    python scripts/Validacao/analise_pronomes_transitividade.py                   # os 3 corpora, lote 10
    python scripts/Validacao/analise_pronomes_transitividade.py --corpus bia --lotes 10
Saída: tabela no terminal e CSV em Outputs/analise_regras/<corpus>/pronomes_transitividade_<lotes>_batches.csv
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path
from typing import Callable, Dict, List, Sequence

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from resultados import (  # noqa: E402
    CORPORA, LexicalMatcher, RobustJSONLReader, Triple, _normalizar_sentenca, achatar_predicoes,
    extrair_triplas,
)

PRONOMES = set("""
eu tu ele ela nós nos vós vos eles elas você vocês me te se lhe lhes o a os as
mim ti si consigo comigo contigo conosco convosco
dele dela deles delas nele nela neles nelas dum duma
isso isto aquilo disso disto daquilo nisso nisto naquilo
este esta estes estas esse essa esses essas aquele aquela aqueles aquelas
deste desta destes destas desse dessa desses dessas daquele daquela daqueles daquelas
neste nesta nestes nestas nesse nessa nesses nessas naquele naquela naqueles naquelas
que quem qual quais onde cujo cuja cujos cujas
""".split())
REL_COPULA = {"é", "são", "foi", "era", "eram", "será"}


def tokens(s: str) -> List[str]:
    s = unicodedata.normalize("NFC", s).lower()
    return [t for t in re.findall(r"[\wáàâãéêíóôõúüç-]+", s) if t]


def norm(s: str) -> str:
    return " ".join(tokens(s))


def so_pronome(arg: str) -> bool:
    t = tokens(arg)
    return bool(t) and all(x in PRONOMES for x in t)


def tem_pronome(t: Triple) -> bool:
    return so_pronome(t.arg1) or so_pronome(t.arg2)


def marcar_transitivas(triplas: Sequence[Triple]) -> List[bool]:
    """True para a tripla (B, R, C) obtida por (A, é, B) + (A, R, C), na mesma sentença."""
    chave = [(norm(t.arg1), norm(t.rel), norm(t.arg2)) for t in triplas]
    existentes = set(chave)
    cop = [(a, b) for (a, r, b) in chave if r in REL_COPULA and a and b and a != b]
    saida = []
    for (b, r, c) in chave:
        derivada = False
        if r not in REL_COPULA:
            for (a, bb) in cop:
                if bb == b and (a, r, c) in existentes:
                    derivada = True
                    break
        saida.append(derivada)
    return saida


def rotular_vp(gold: Sequence[Triple], pred: Sequence[Triple], matcher: LexicalMatcher) -> List[bool]:
    """Mesmo casamento guloso 1 para 1 do resultados.py, mas devolvendo, para cada predição, se foi VP."""
    usadas, saida = set(), []
    for p in pred:
        ok = False
        for i, g in enumerate(gold):
            if i not in usadas and matcher.bate(g, p):
                usadas.add(i)
                ok = True
                break
        saida.append(ok)
    return saida


def f1(vp: int, fp: int, fn: int) -> float:
    p = vp / (vp + fp) if vp + fp else 0.0
    r = vp / (vp + fn) if vp + fn else 0.0
    return 2 * p * r / (p + r) if p + r else 0.0


def prec(vp: int, n: int) -> float:
    return vp / n if n else float("nan")


def carregar_gold(caminho: str) -> Dict[str, List[Triple]]:
    objs = achatar_predicoes(RobustJSONLReader(Path(caminho)).carregar().objetos)
    return {_normalizar_sentenca(o.get("sentence", "")): extrair_triplas(o) for o in objs if isinstance(o, dict)}


def analisar_sistema(gold: Dict[str, List[Triple]], caminho: Path, matcher: LexicalMatcher) -> dict:
    objs = achatar_predicoes(RobustJSONLReader(caminho).carregar().objetos)
    por_sent = {}
    for o in objs:
        if isinstance(o, dict):
            por_sent[_normalizar_sentenca(o.get("sentence", ""))] = extrair_triplas(o)

    acc = {k: 0 for k in ("n", "vp", "n_pron", "vp_pron", "n_trans", "vp_trans", "fn_total",
                          "vp_sem_pron", "fp_sem_pron", "vp_sem_trans", "fp_sem_trans")}
    fn_sem_pron = fn_sem_trans = 0
    for chave, g in gold.items():
        pred = por_sent.get(chave, [])
        vp_flags = rotular_vp(g, pred, matcher)
        pron_flags = [tem_pronome(t) for t in pred]
        trans_flags = marcar_transitivas(pred)

        acc["n"] += len(pred)
        acc["vp"] += sum(vp_flags)
        acc["n_pron"] += sum(pron_flags)
        acc["vp_pron"] += sum(v and p for v, p in zip(vp_flags, pron_flags))
        acc["n_trans"] += sum(trans_flags)
        acc["vp_trans"] += sum(v and t for v, t in zip(vp_flags, trans_flags))
        acc["fn_total"] += len(g) - sum(vp_flags)

        for nome, flags in (("pron", pron_flags), ("trans", trans_flags)):
            filtradas = [t for t, f in zip(pred, flags) if not f]
            v2 = sum(rotular_vp(g, filtradas, matcher))
            acc[f"vp_sem_{nome}"] += v2
            acc[f"fp_sem_{nome}"] += len(filtradas) - v2
            if nome == "pron":
                fn_sem_pron += len(g) - v2
            else:
                fn_sem_trans += len(g) - v2

    vp, n = acc["vp"], acc["n"]
    return {
        "n_triplas": n,
        "precisao_lex": round(prec(vp, n), 3),
        "f1_lex": round(f1(vp, n - vp, acc["fn_total"]), 3),
        "n_pronome": acc["n_pron"],
        "pct_pronome": round(acc["n_pron"] / n, 3) if n else float("nan"),
        "prec_pronome": round(prec(acc["vp_pron"], acc["n_pron"]), 3),
        "prec_sem_pronome": round(prec(acc["vp_sem_pron"], acc["vp_sem_pron"] + acc["fp_sem_pron"]), 3),
        "f1_sem_pronome": round(f1(acc["vp_sem_pron"], acc["fp_sem_pron"], fn_sem_pron), 3),
        "n_transitiva": acc["n_trans"],
        "pct_transitiva": round(acc["n_trans"] / n, 3) if n else float("nan"),
        "prec_transitiva": round(prec(acc["vp_trans"], acc["n_trans"]), 3),
        "f1_sem_transitiva": round(f1(acc["vp_sem_trans"], acc["fp_sem_trans"], fn_sem_trans), 3),
    }


def resumo_gold(gold: Dict[str, List[Triple]]) -> dict:
    todas = [t for g in gold.values() for t in g]
    n_trans = sum(sum(marcar_transitivas(g)) for g in gold.values())
    n_pron = sum(tem_pronome(t) for t in todas)
    return {"n_triplas": len(todas), "n_pronome": n_pron,
            "pct_pronome": round(n_pron / len(todas), 3) if todas else float("nan"),
            "n_transitiva": n_trans,
            "pct_transitiva": round(n_trans / len(todas), 3) if todas else float("nan")}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", nargs="*", default=["bia", "oiec_pt", "oiec_pt_abs"])
    ap.add_argument("--lotes", type=int, default=10)
    ap.add_argument("--limiar-lexical", type=float, default=0.5)
    a = ap.parse_args()

    matcher = LexicalMatcher(limiar=a.limiar_lexical)
    pd.set_option("display.width", 250, "display.max_columns", 30)
    for corpus in a.corpus:
        cfg = CORPORA[corpus]
        gold = carregar_gold(cfg["gold"])
        print(f"\n{'=' * 100}\nCORPUS {corpus}  (gold: {cfg['gold']})\n{'=' * 100}")
        print("GOLD:", resumo_gold(gold))

        base = Path(cfg["respostas"]) / f"{a.lotes}_batches"
        linhas = []
        for pasta in sorted(p for p in base.glob("Respostas*") if p.is_dir()):
            for arq in sorted(pasta.glob("*.jsonl")):
                r = analisar_sistema(gold, arq, matcher)
                linhas.append({"corpus": corpus, "pasta": pasta.name.replace("Respostas ", ""), "modelo": arq.stem, **r})
        if not linhas:
            print("   (nenhuma resposta encontrada em", base, ")")
            continue
        df = pd.DataFrame(linhas)
        print("\n-- Pronome só no argumento (BIA invalida; OIEC-PT aceita)")
        print(df[["pasta", "modelo", "n_triplas", "n_pronome", "pct_pronome", "prec_pronome",
                  "prec_sem_pronome", "f1_lex", "f1_sem_pronome"]].to_string(index=False))
        print("\n-- Padrão de transitividade (OIEC-PT S5 não valida; DptOIE gera)")
        print(df[["pasta", "modelo", "n_triplas", "n_transitiva", "pct_transitiva", "prec_transitiva",
                  "f1_lex", "f1_sem_transitiva"]].to_string(index=False))

        saida = Path("Outputs") / "analise_regras" / corpus
        saida.mkdir(parents=True, exist_ok=True)
        csv = saida / f"pronomes_transitividade_{a.lotes}_batches.csv"
        df.to_csv(csv, index=False)
        print("\nCSV:", csv)


if __name__ == "__main__":
    main()
