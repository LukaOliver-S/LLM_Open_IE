"""Converte dados/oiec_pt_gold_abstractive_silver.json (referência silver abstrativa da tese de
Cabral, 2025: 100 sentenças do OIEC-PT Gold, 238 triplas geradas pelo Gemini 2.5 Pro) para o
formato de gold do pipeline.

Saída: dados/oiec_pt_abs_gold_sentences.jsonl, uma linha por sentença, NA MESMA ORDEM E COM O MESMO
TEXTO do corpus oiec_pt (dados/oiec_pt_gold_sentences.jsonl). Assim o corpus novo (oiec_pt_abs)
reaproveita os lotes de sentencas_oiecpt/ e as saídas dos modelos locais já rodadas no oiec_pt.

Só o gold muda: as sentenças vêm do oiec_pt, as triplas vêm do silver. Casamento pelo número do
documento (doc_id do oiec_pt == pud_id do silver), conferido pela semelhança do texto.

Uso (da raiz do repositório):
    python scripts/formatacao/converter_abstractive_silver.py
"""
from __future__ import annotations

import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SILVER = RAIZ / "dados" / "oiec_pt_gold_abstractive_silver.json"
GOLD_OIEC = RAIZ / "dados" / "oiec_pt_gold_sentences.jsonl"
SAIDA = RAIZ / "dados" / "oiec_pt_abs_gold_sentences.jsonl"
LIMIAR_TEXTO = 0.97   # as sentenças só diferem em espaços ao redor de hífens (ver nota abaixo)


def norm(s: str) -> str:
    """Texto comparável: NFC, minúsculas, sem espaços ao redor de hífens/travessões, espaços únicos."""
    s = unicodedata.normalize("NFC", s).lower()
    s = re.sub(r"\s*([-–—])\s*", r"\1", s)
    return re.sub(r"\s+", " ", s).strip()


def main() -> None:
    silver = json.loads(SILVER.read_text(encoding="utf-8"))
    por_pud = {int(it["pud_id"]): it for it in silver["items"]}
    if len(por_pud) != len(silver["items"]):
        raise SystemExit("pud_id repetido no silver")

    linhas = [json.loads(l) for l in GOLD_OIEC.read_text(encoding="utf-8").splitlines() if l.strip()]
    usados, saida, divergentes = set(), [], []
    for reg in linhas:
        pud = int(reg["doc_id"])
        it = por_pud.get(pud)
        if it is None:
            raise SystemExit(f"doc_id {pud} do oiec_pt não existe no silver")
        sim = SequenceMatcher(None, norm(reg["sentence"]), norm(it["sentence"])).ratio()
        if sim < LIMIAR_TEXTO:
            divergentes.append((pud, round(sim, 3), reg["sentence"][:70], it["sentence"][:70]))
        usados.add(pud)
        triplas = [
            {"arg1": e["arg1"], "rel": e.get("rel", ""), "arg2": e["arg2"], "valid": True}
            for e in it["extractions"]
            if e.get("arg1") and e.get("arg2")
        ]
        saida.append({
            "doc_id": reg["doc_id"],
            "phrase_index": reg.get("phrase_index"),
            "sentence": reg["sentence"],          # texto do oiec_pt (não o do silver)
            "gold": triplas,
            "referencia": "silver_gemini_2.5_pro",
        })

    faltando = set(por_pud) - usados
    if divergentes or faltando:
        for d in divergentes:
            print("TEXTO DIVERGENTE:", d)
        raise SystemExit(f"abortado: {len(divergentes)} textos divergentes, {len(faltando)} pud_id sem par")

    SAIDA.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in saida) + "\n", encoding="utf-8")
    n_tr = sum(len(r["gold"]) for r in saida)
    vazias = sum(1 for r in saida if not r["gold"])
    print(f"gravado: {SAIDA}")
    print(f"{len(saida)} sentenças, {n_tr} triplas, {vazias} sentenças sem tripla")


if __name__ == "__main__":
    main()
