# -*- coding: utf-8 -*-
"""
converter_oiec_pt_gold.py
===========================
Converte dados/OIEC-PT-GOLD.txt (formato TSV do artigo "Challenges in
Expanding Portuguese Resources") para o mesmo formato JSONL usado por
dados/bia_gold_sentences.jsonl -- assim, todo o pipeline de avaliação já
existente (resultados.py, comparação_batches.py, contagem_triplas.py,
graficos_resumo.py, checagem_consenso.py) funciona sem nenhuma mudança,
bastando apontar --gold (ou GOLD_PADRAO) para o arquivo gerado aqui.

Formato de entrada (TSV):
- Linha de sentença: 2 campos -- {id}\t{texto da sentença}
- Linha de tripla candidata: 6 campos -- arg1\trel\targ2\tflag1\tflag2\tflag3

Uso: `python converter_oiec_pt_gold.py`, rodando de dentro de
scripts/formatacao/ com o cwd na raiz do projeto.
"""

from __future__ import annotations

import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]  # LLM_Open_IE/
ENTRADA = RAIZ / "dados" / "OIEC-PT-GOLD.txt"
SAIDA_GOLD = RAIZ / "dados" / "oiec_pt_gold_sentences.jsonl"
SAIDA_SENTENCAS = RAIZ / "dados" / "oiec_pt_apenas_sentencas.jsonl"


def parse_oiec_pt_gold(caminho: Path) -> list[dict]:
    """Lê o TSV e devolve uma lista de sentenças no mesmo formato de
    dados/bia_gold_sentences.jsonl: {"doc_id", "phrase_index", "sentence", "gold": [...]}."""
    linhas = caminho.read_text(encoding="utf-8").splitlines()

    sentencas: list[dict] = []
    atual: dict | None = None

    for numero_linha, linha in enumerate(linhas, start=1):
        if not linha.strip():
            continue
        campos = linha.split("\t")

        if len(campos) == 2:
            if atual is not None:
                sentencas.append(atual)
            pud_id, texto = campos
            atual = {
                "doc_id": int(pud_id) if pud_id.strip().isdigit() else pud_id,
                "phrase_index": len(sentencas),
                "sentence": texto,
                "gold": [],
            }
        elif len(campos) == 6:
            if atual is None:
                raise ValueError(f"Linha {numero_linha}: tripla antes de qualquer sentença: {linha[:80]!r}")
            arg1, rel, arg2, flag1, flag2, flag3 = campos
            if flag2.strip() == "1":
                atual["gold"].append({"arg1": arg1, "rel": rel, "arg2": arg2, "valid": True})
        else:
            raise ValueError(f"Linha {numero_linha} com formato inesperado ({len(campos)} campos): {linha[:80]!r}")

    if atual is not None:
        sentencas.append(atual)

    return sentencas


def main() -> None:
    sentencas = parse_oiec_pt_gold(ENTRADA)

    total_triplas = sum(len(s["gold"]) for s in sentencas)
    print(f"Sentenças: {len(sentencas)}")
    print(f"Triplas válidas (gold, flag do meio == 1): {total_triplas}")

    with open(SAIDA_GOLD, "w", encoding="utf-8") as f:
        for s in sentencas:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"Gold salvo em: {SAIDA_GOLD}")

    with open(SAIDA_SENTENCAS, "w", encoding="utf-8") as f:
        for s in sentencas:
            f.write(json.dumps({"sentence": s["sentence"]}, ensure_ascii=False) + "\n")
    print(f"Sentenças (sem gold) salvas em: {SAIDA_SENTENCAS}")


if __name__ == "__main__":
    main()
