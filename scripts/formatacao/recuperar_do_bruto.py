"""Recupera, a partir do texto bruto (_bruto/<tarefa>/<modelo>/parte_N.txt), as sentenças que ficaram
de fora do arquivo final de respostas, em geral porque a linha estava com JSON inválido (aspas sem escape etc.)
e foi descartada na montagem. As linhas passam pela mesma correção de corrigir_jsonl.py.

Só ACRESCENTA sentenças que existem no corpus e faltam no arquivo final. Nunca altera as que já estão lá.
O arquivo final é regravado na ORDEM DO CORPUS. Sentenças que nem o bruto tem são listadas (precisam de recoleta).

Uso (da raiz do repositório):
    python scripts/formatacao/recuperar_do_bruto.py \\
        --final "Respostas/oiec_pt/10_batches/Respostas ExtrativoDPTO-IE/respostas_gpt5.5_mini.jsonl" \\
        --bruto "Respostas/oiec_pt/10_batches/_bruto/dpto/respostas_gpt5.5_mini" \\
        --sentencas sentencas_oiecpt/10_sentencas              # relatório, não grava
    (acrescente --aplicar para gravar; o original fica em <arquivo>.pre_recuperacao.bak)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corrigir_jsonl import INICIO, corrigir_linha   # noqa: E402


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s).lower()).strip()


def ler_corpus(pasta: Path) -> list[str]:
    frases = []
    for p in sorted(pasta.glob("sentencas_parte_*.jsonl"), key=lambda x: int(re.search(r"(\d+)", x.stem[16:]).group(1))):
        frases += [json.loads(l)["sentence"] for l in p.read_text(encoding="utf-8").split("\n") if l.strip()]
    return frases


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--final", required=True, help="arquivo .jsonl final do modelo")
    ap.add_argument("--bruto", required=True, help="pasta com parte_N.txt do mesmo modelo/tarefa")
    ap.add_argument("--sentencas", required=True, help="pasta com sentencas_parte_N.jsonl (a ordem do corpus)")
    ap.add_argument("--aplicar", action="store_true")
    a = ap.parse_args()

    final, bruto = Path(a.final), Path(a.bruto)
    corpus = ler_corpus(Path(a.sentencas))
    chaves = {norm(s) for s in corpus}

    existentes: dict[str, str] = {}
    for l in final.read_text(encoding="utf-8").split("\n"):
        if l.strip():
            try:
                existentes[norm(json.loads(l)["sentence"])] = l
            except Exception:
                pass                                   # linha inválida que não deveria existir: não é tratada aqui

    recuperadas: dict[str, str] = {}
    for p in sorted(bruto.glob("parte_*.txt")):
        for l in p.read_text(encoding="utf-8").split("\n"):
            if not INICIO.match(l):
                continue
            linhas, feitos = corrigir_linha(l)
            for nova in linhas:
                try:
                    k = norm(json.loads(nova)["sentence"])
                except Exception:
                    continue
                if k in chaves and k not in existentes and k not in recuperadas:
                    recuperadas[k] = nova
                    print(f"  recuperada ({p.name}, correção: {feitos or 'nenhuma'}): {json.loads(nova)['sentence'][:80]}")

    sem_nada = [s for s in corpus if norm(s) not in existentes and norm(s) not in recuperadas]
    print(f"\n{final.name}: tinha {len(existentes)} de {len(corpus)}; recuperadas {len(recuperadas)}; "
          f"ainda faltando {len(sem_nada)}")
    for s in sem_nada:
        print("   FALTA (precisa recoletar):", s[:90])

    if recuperadas and a.aplicar:
        bak = final.with_name(final.name + ".pre_recuperacao.bak")
        if not bak.exists():
            bak.write_text(final.read_text(encoding="utf-8"), encoding="utf-8", newline="")
        todas = {**existentes, **recuperadas}
        final.write_text("\n".join(todas[norm(s)] for s in corpus if norm(s) in todas) + "\n",
                         encoding="utf-8", newline="")
        print("gravado.")
    elif recuperadas:
        print("(relatório: nada foi gravado; use --aplicar)")


if __name__ == "__main__":
    main()
