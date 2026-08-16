# scripts/Validacao/bootstrap_carb.py
"""
Bootstrap sobre as FRASES, pontuando com CaRB (carb_score.py).
Entrega, por modelo: F1-CaRB + IC 95%. E teste pareado PTOIE-Flair vs cada LLM
(reamostrando as MESMAS frases pros dois -> diferença pareada + p-valor).

Uso:
    python -X utf8 scripts/Validacao/bootstrap_carb.py --corpus oiec_pt --tarefa dpto --B 2000
"""
from __future__ import annotations
import argparse, json, random, sys
from difflib import SequenceMatcher
from pathlib import Path
import numpy as np

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "scripts" / "Validacao"))
from resultados import CORPORA
from carb_score import Tripla, score_sentenca, agregar, tokens

CATEGORIA = {"abstractive": "Respostas AbstractiveOpenIE", "dpto": "Respostas ExtrativoDPTO-IE",
             "oiec": "Respostas ExtrativoOIEC-PT", "ptoiedp": "Respostas ExtrativoPTOIE-DP"}


def carregar_jsonl(p: Path):
    """Aceita QUALQUER combinação: JSONL, um array JSON, ou vários arrays/objetos
    concatenados (o caso do Gemini). Varre com raw_decode, um valor por vez, e
    coleta todos os dicts encontrados."""
    texto = p.read_text(encoding="utf-8").strip()
    if not texto:
        return []
    dec = json.JSONDecoder()
    out, i, n = [], 0, len(texto)
    while i < n:
        while i < n and texto[i] in " \t\r\n,":       # pula separadores
            i += 1
        if i >= n:
            break
        try:
            val, j = dec.raw_decode(texto, i)
        except json.JSONDecodeError:
            nl = texto.find("\n", i)                   # trecho ruim: pula a linha
            if nl == -1:
                break
            i = nl + 1
            continue
        i = j
        if isinstance(val, dict):
            out.append(val)
        elif isinstance(val, list):
            out.extend(x for x in val if isinstance(x, dict))
    return out


def triplas_de(relations):
    # gold usa r["valid"]; predições não têm o campo -> default True (incluídas)
    return [Tripla(str(r.get("arg1", "")), str(r.get("rel", "")), str(r.get("arg2", "")))
            for r in relations if isinstance(r, dict) and r.get("valid", True) is not False]


def parear(preds, gold):
    """idx_gold -> lista de triplas preditas (por texto normalizado).
    Match exato (dict, O(1)) primeiro; fuzzy só pros que sobrarem."""
    gnorm = [" ".join(tokens(g["sentence"])) for g in gold]
    exato = {}
    for i, gn in enumerate(gnorm):
        exato.setdefault(gn, i)                     # 1ª ocorrência do texto
    usados, mapa, faltam = set(), {}, []
    for p in preds:
        s = " ".join(tokens(p.get("sentence", "")))
        i = exato.get(s)
        if i is not None and i not in usados:
            usados.add(i)
            mapa[i] = triplas_de(p.get("relations", []))
        else:
            faltam.append(p)                        # texto diferente/repetido -> fuzzy
    for p in faltam:
        s = " ".join(tokens(p.get("sentence", "")))
        bi, br = None, 0.0
        for i, gn in enumerate(gnorm):
            if i in usados:
                continue
            r = SequenceMatcher(None, s, gn).ratio()
            if r > br:
                bi, br = i, r
        if bi is not None and br >= 0.90:
            usados.add(bi)
            mapa[bi] = triplas_de(p.get("relations", []))
    return mapa


def acumuladores_modelo(pred_path: Path, gold):
    """Lista alinhada ao gold: um (pn,pd,rn,rd) por frase."""
    mapa = parear(carregar_jsonl(pred_path), gold)
    acc = []
    for i, g in enumerate(gold):
        gold_trs = triplas_de(g.get("gold", []))     # gold guarda triplas em "gold"
        pred_trs = mapa.get(i, [])
        acc.append(score_sentenca(gold_trs, pred_trs))
    return acc   # len == len(gold), mesma ordem p/ todos os modelos


def f1_de(acc, idx):
    return agregar([acc[i] for i in idx])["f1"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="bia", choices=list(CORPORA))
    ap.add_argument("--tarefa", default="dpto", choices=list(CATEGORIA))
    ap.add_argument("--B", type=int, default=2000, help="nº de reamostragens")
    ap.add_argument("--ref", default="PTOIE-Flair", help="modelo de referência p/ o teste pareado")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    random.seed(args.seed)
    rng = np.random.default_rng(args.seed)

    cfg = CORPORA[args.corpus]
    gold = [json.loads(l) for l in
            Path(RAIZ / cfg["gold"]).read_text(encoding="utf-8").splitlines() if l.strip()]
    pasta = RAIZ / cfg["respostas"] / "10_batches" / CATEGORIA[args.tarefa]

    modelos = {mp.stem: acumuladores_modelo(mp, gold) for mp in sorted(pasta.glob("*.jsonl"))}
    n = len(gold)
    # B matrizes de índices reamostrados (as MESMAS p/ todos os modelos -> pareado)
    amostras = [rng.integers(0, n, size=n) for _ in range(args.B)]

    print(f"\ncorpus={args.corpus} tarefa={args.tarefa} B={args.B} n={n}\n")
    print(f"{'modelo':26} {'F1':>7} {'IC95%':>18}")
    dist = {}
    for m, acc in modelos.items():
        pontual = agregar(acc)["f1"]
        boot = np.array([f1_de(acc, idx) for idx in amostras])
        dist[m] = boot
        lo, hi = np.percentile(boot, [2.5, 97.5])
        print(f"{m:26} {pontual:>7.3f}   [{lo:.3f}, {hi:.3f}]")

    # teste pareado: ref - LLM, com as mesmas reamostragens
    if args.ref in dist:
        print(f"\nDiferença pareada (F1[{args.ref}] - F1[modelo]):")
        for m in dist:
            if m == args.ref:
                continue
            d = dist[args.ref] - dist[m]
            lo, hi = np.percentile(d, [2.5, 97.5])
            p = 2 * min((d <= 0).mean(), (d >= 0).mean())   # p bilateral
            sig = "sig." if lo > 0 or hi < 0 else "n.s."
            print(f"  vs {m:24} Δ={d.mean():+.3f}  IC[{lo:+.3f},{hi:+.3f}]  p≈{p:.3f}  {sig}")


if __name__ == "__main__":
    main()
