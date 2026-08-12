#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
criar_unified.py
================

Cria o corpus UNIFIED = BIA (262) + OIEC-PT (100) = 362 frases, EMBARALHADO com
seed fixo (42, reproduzível), para testar generalização de convenções mistas.

Cada frase carrega o campo `source` ("bia"/"oiec") — assim, mesmo embaralhado
para a coleta (cega), dá para quebrar os resultados por origem depois.

Gera:
  - dados/unified_gold_sentences.jsonl   (gold unificado, com `source`)
  - sentencas_unified/10_sentencas/sentencas_parte_*.jsonl  (batches p/ coleta)
  - dados/unified_sentences.txt          (frases p/ os extratores especializados)

USO:  python scripts/formatacao/criar_unified.py
"""

import json
import random
from pathlib import Path

SEED = 42
POR_PARTE = 10   # frases por batch de coleta

FONTES = [
    ("dados/bia_gold_sentences.jsonl", "bia"),
    ("dados/oiec_pt_gold_sentences.jsonl", "oiec"),
]


def carregar(caminho, source):
    regs = []
    for linha in open(caminho, encoding="utf-8"):
        if not linha.strip():
            continue
        obj = json.loads(linha)
        obj["source"] = source        # etiqueta de origem (preservada no gold)
        regs.append(obj)
    return regs


def main():
    # 1. junta os dois, etiquetando a origem
    regs = []
    for caminho, source in FONTES:
        parte = carregar(caminho, source)
        regs.extend(parte)
        print(f"  {source}: {len(parte)} frases")
    print(f"total merged: {len(regs)}")

    # 2. embaralha com seed FIXO (reproduzível)
    random.seed(SEED)
    random.shuffle(regs)
    print(f"embaralhado com seed={SEED}")

    # 2b. renumera o doc_id no contexto do unified. O original mistura dois esquemas
    #     (BIA 1.. e OIEC 201..) e não faz sentido junto -> id sequencial novo (1..N),
    #     preservando o original em 'orig_doc_id'.
    for i, r in enumerate(regs, start=1):
        r["orig_doc_id"] = r.pop("doc_id", None)
        r["doc_id"] = i

    # 3. gold unificado (na ordem embaralhada, com `source`)
    Path("dados").mkdir(exist_ok=True)
    gold_out = "dados/unified_gold_sentences.jsonl"
    with open(gold_out, "w", encoding="utf-8") as f:
        for r in regs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"gold  -> {gold_out}")

    # 4. batches de coleta. Guardamos 'source' junto pra rastreio; a coleta
    #    continua CEGA porque o assistente_coleta só usa o campo 'sentence' no prompt.
    pasta = Path("sentencas_unified") / "10_sentencas"
    pasta.mkdir(parents=True, exist_ok=True)
    n_partes = 0
    for i in range(0, len(regs), POR_PARTE):
        n_partes += 1
        with open(pasta / f"sentencas_parte_{n_partes}.jsonl", "w", encoding="utf-8") as f:
            for r in regs[i:i + POR_PARTE]:
                f.write(json.dumps({"sentence": r["sentence"], "source": r["source"]}, ensure_ascii=False) + "\n")
    print(f"batches -> {pasta}/  ({n_partes} partes de até {POR_PARTE})")

    # 5. txt (mesma ordem embaralhada) para os extratores especializados
    txt_out = "dados/unified_sentences.txt"
    with open(txt_out, "w", encoding="utf-8", newline="\n") as f:
        for r in regs:
            f.write(r["sentence"].replace("\r", " ").replace("\n", " ").strip() + "\n")
    print(f"txt   -> {txt_out}")

    # 6. apenas_sentencas (mesmo formato dos outros corpora: {"sentence": ...})
    ap_out = "dados/unified_apenas_sentencas.jsonl"
    with open(ap_out, "w", encoding="utf-8") as f:
        for r in regs:
            f.write(json.dumps({"sentence": r["sentence"]}, ensure_ascii=False) + "\n")
    print(f"apenas_sentencas -> {ap_out}")

    print(f"\nOK — corpus 'unified' criado ({len(regs)} frases). "
          f"Rode a coleta/pipeline com --corpus unified.")


if __name__ == "__main__":
    main()
