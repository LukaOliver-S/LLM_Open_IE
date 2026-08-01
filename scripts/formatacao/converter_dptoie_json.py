#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
converter_dptoie_json.py
========================

Converte a saída JSON do DptOIE (`-ot json`) para o JSONL que o pipeline espera.

O DptOIE (-ot json) devolve um ARRAY de objetos:
    [{"sentence": "...", "extractions": [{"arg1","rel","arg2", "sub_extractions": [...]?}, ...]}, ...]

O pipeline (resultados.py) espera JSONL (um objeto por linha) com a chave `relations`:
    {"sentence": "...", "relations": [{"arg1","rel","arg2"}, ...]}

Este script:
1. Lê o array JSON do DptOIE.
2. Converte `extractions` -> `relations`.
3. Se uma extração tiver `arg2` vazio E tiver `sub_extractions`, reconstrói o arg2
   juntando o conteúdo das sub-extrações (e mantém as subs como triplas próprias).
4. Remove triplas exatamente duplicadas.
5. Alinha as frases ao gold (reusa a normalização robusta a contrações do
   corrigir_dptoie.py), e escreve JSONL alinhado ao gold.

USO
----
    python3 converter_dptoie_json.py entrada.json [saida.jsonl] --gold dados/bia_gold_sentences.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

# Reusa norm(), carregar_frases_gold() e alinhar_ao_gold() do corrigir_dptoie.py
sys.path.insert(0, str(Path(__file__).resolve().parent))
from corrigir_dptoie import carregar_frases_gold, alinhar_ao_gold  # noqa: E402


def _campo(d: dict, *chaves: str) -> str:
    """Pega o primeiro campo não-vazio dentre as chaves possíveis (robusto a
    variações de nome: arg1/subject, rel/relation, arg2/object)."""
    for k in chaves:
        v = d.get(k)
        if v:
            return str(v).strip()
    return ""


def montar_relations(obj: dict) -> List[Dict[str, str]]:
    """Constrói a lista `relations` a partir de `extractions` (+ sub_extractions)."""
    rels: List[Dict[str, str]] = []
    for ext in obj.get("extractions", []) or []:
        if not isinstance(ext, dict):
            continue
        a1 = _campo(ext, "arg1", "subject", "arg_1")
        rel = _campo(ext, "rel", "relation", "relação")
        a2 = _campo(ext, "arg2", "object", "arg_2")
        subs = ext.get("sub_extractions") or ext.get("subextractions") or []

        # arg2 vazio + tem subs -> reconstrói o arg2 com o conteúdo das subs
        if not a2 and subs:
            partes = []
            for s in subs:
                if isinstance(s, dict):
                    txt = " ".join(t for t in (
                        _campo(s, "arg1", "subject"),
                        _campo(s, "rel", "relation"),
                        _campo(s, "arg2", "object"),
                    ) if t).strip()
                    if txt:
                        partes.append(txt)
            a2 = " ; ".join(partes)

        if a1 or rel or a2:
            rels.append({"arg1": a1, "rel": rel, "arg2": a2})

        # mantém as subs também como triplas próprias
        for s in subs:
            if not isinstance(s, dict):
                continue
            sa1 = _campo(s, "arg1", "subject")
            sr = _campo(s, "rel", "relation")
            sa2 = _campo(s, "arg2", "object")
            if sa1 or sr or sa2:
                rels.append({"arg1": sa1, "rel": sr, "arg2": sa2})

    # dedup exato (mesmo arg1/rel/arg2, ignorando caixa)
    vistos: set = set()
    saida: List[Dict[str, str]] = []
    for r in rels:
        chave = (r["arg1"].lower(), r["rel"].lower(), r["arg2"].lower())
        if chave in vistos:
            continue
        vistos.add(chave)
        saida.append(r)
    return saida


def carregar_json_dptoie(caminho: Path) -> List[dict]:
    """Lê o array JSON do DptOIE (ou, defensivamente, JSONL)."""
    txt = caminho.read_text(encoding="utf-8", errors="replace").strip()
    try:
        dados = json.loads(txt)
        if isinstance(dados, list):
            return [o for o in dados if isinstance(o, dict)]
        if isinstance(dados, dict):
            return [dados]
    except json.JSONDecodeError:
        pass
    # fallback: uma linha por objeto
    out = []
    for l in txt.splitlines():
        l = l.strip()
        if not l:
            continue
        try:
            out.append(json.loads(l))
        except json.JSONDecodeError:
            pass
    return [o for o in out if isinstance(o, dict)]


def main():
    args = sys.argv[1:]
    if not args or "--gold" not in args:
        print("Uso: python3 converter_dptoie_json.py entrada.json [saida.jsonl] --gold dados/bia_gold_sentences.jsonl")
        sys.exit(1)

    idx_gold = args.index("--gold")
    caminho_gold = Path(args[idx_gold + 1])
    del args[idx_gold: idx_gold + 2]

    caminho_entrada = Path(args[0])
    caminho_saida = Path(args[1]) if len(args) >= 2 else \
        caminho_entrada.with_suffix(".jsonl")

    for p in (caminho_entrada, caminho_gold):
        if not p.exists():
            print(f"❌ Arquivo não encontrado: {p}")
            sys.exit(1)

    print(f"Lendo JSON do DptOIE: {caminho_entrada}")
    objetos = carregar_json_dptoie(caminho_entrada)
    preds = [{"sentence": o.get("sentence", ""), "relations": montar_relations(o)} for o in objetos]
    total_tri = sum(len(p["relations"]) for p in preds)
    print(f"-> {len(preds)} frase(s), {total_tri} tripla(s) (após dedup)")

    frases_gold = carregar_frases_gold(caminho_gold)
    saida, n_ex, n_fz, n_falt = alinhar_ao_gold(preds, frases_gold)
    print(f"-> alinhado ao gold: exato={n_ex} fuzzy={n_fz} sem_predição={n_falt}")

    with open(caminho_saida, "w", encoding="utf-8") as f:
        for item in saida:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"✅ JSONL salvo em: {caminho_saida}")


if __name__ == "__main__":
    main()
