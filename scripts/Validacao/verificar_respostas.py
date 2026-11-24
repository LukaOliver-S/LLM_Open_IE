#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verificar_respostas.py
=======================

Confere os arquivos de resposta (Respostas/<corpus>/<N>_batches/Respostas*/*.jsonl) contra o gold e aponta
sentenças DUPLICADAS e FALTANDO, e em QUAIS LOTES as que faltam estão. Só lê, não altera nada.

Serve para pegar erros de colagem logo depois de coletar um modelo (um lote colado no lugar de outro deixa
o lote certo sem resposta e o outro duplicado).

Leitura do relatório
  duplicadas / faltando >= 3   quase sempre um lote colado errado: veja a coluna "lotes sem resposta" e
                               recolete esses lotes com `assistente_coleta.py ... --apenas-lotes N`.
  duplicadas = faltando = 1 ou 2   em geral o modelo alterou o texto da sentença ao copiá-la (coluna
                               "texto alterado"). O avaliador não casa essa sentença. É pequeno e esperado.

USO (da raiz do repositório)
    python scripts/Validacao/verificar_respostas.py                       # os 3 corpora
    python scripts/Validacao/verificar_respostas.py --corpus bia --filtro ExtrativoBIA
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from resultados import CORPORA, RobustJSONLReader, _normalizar_sentenca as N, achatar_predicoes  # noqa: E402

logging.disable(logging.CRITICAL)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", nargs="*", default=["bia", "oiec_pt", "oiec_pt_abs"])
    ap.add_argument("--lotes", type=int, default=10)
    ap.add_argument("--filtro", default="", help="só pastas cujo nome contém este texto (ex.: ExtrativoBIA)")
    a = ap.parse_args()

    total = 0
    for c in a.corpus:
        cfg = CORPORA[c]
        gold = [N(json.loads(l)["sentence"]) for l in Path(cfg["gold"]).read_text(encoding="utf-8").split("\n") if l.strip()]
        G = set(gold)
        lote_de = {}
        pasta_sent = Path(cfg["sentencas"]) / f"{a.lotes}_sentencas"
        for p in sorted(pasta_sent.glob("sentencas_parte_*.jsonl")):
            n_lote = int(p.stem.rsplit("_", 1)[1])
            for l in p.read_text(encoding="utf-8").split("\n"):
                if l.strip():
                    lote_de[N(json.loads(l)["sentence"])] = n_lote
        base = Path(cfg["respostas"]) / f"{a.lotes}_batches"
        for pasta in sorted(p for p in base.glob("Respostas*") if p.is_dir() and a.filtro in p.name):
            for f in sorted(pasta.glob("*.jsonl")):
                objs = achatar_predicoes(RobustJSONLReader(f).carregar().objetos)
                chaves = [N(o.get("sentence", "")) for o in objs if isinstance(o, dict)]
                cont = Counter(chaves)
                dup = sum(v - 1 for v in cont.values() if v > 1)
                falt = G - set(chaves)
                fora = set(chaves) - G
                if not (dup or falt or fora):
                    continue
                lotes_falt = sorted({lote_de.get(s, "?") for s in falt})
                alerta = "  <-- provável lote colado errado" if (dup >= 3 or len(falt) >= 3) else ""
                print(f"{c:11} {pasta.name[10:]:20} {f.stem:28} registros={len(chaves):3d} duplicadas={dup:3d} "
                      f"faltando={len(falt):3d} texto_alterado={len(fora):2d} lotes_sem_resposta={lotes_falt}{alerta}")
                total += 1
    print(f"\n{total} arquivo(s) com alguma divergência." if total else "\nNenhuma divergência: todos os arquivos cobrem o gold.")


if __name__ == "__main__":
    main()
