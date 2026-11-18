"""Corrige defeitos de formato em respostas .jsonl (uma sentença por linha) sem mexer no conteúdo.

Defeitos tratados (só em linhas que começam com {"sentence"):
  1. `\\` solto no fim da linha (vem da cópia do chat)      -> removido
  2. aspas internas sem escape no campo "sentence"        -> escapadas (\\")
Arquivos que não são de uma linha por sentença (JSON indentado em várias linhas) são ignorados.
Linhas que continuam inválidas depois da correção ficam como estavam e são listadas.

Uso (da raiz do repositório):
    python scripts/formatacao/corrigir_jsonl.py                 # só relatório, não altera nada
    python scripts/formatacao/corrigir_jsonl.py --aplicar       # grava, guardando o original em <arquivo>.pre_correcao.bak
    python scripts/formatacao/corrigir_jsonl.py --raiz "Respostas/oiec_pt"   # restringe a uma pasta
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
ABRE = '{"sentence":"'
PADRAO = re.compile(r'^\{"sentence":\s*"(?P<s>.*?)"\s*,\s*"relations"\s*:\s*(?P<r>\[.*\])\s*\}$', re.S)


def valido(linha: str) -> bool:
    try:
        json.loads(linha)
        return True
    except Exception:
        return False


def corrigir_linha(linha: str) -> tuple[str, list[str]]:
    """Devolve (linha_corrigida, defeitos_corrigidos). Se não der para corrigir, devolve a original."""
    feitos: list[str] = []
    atual = linha.rstrip()
    if atual.endswith("\\") and not valido(atual):
        atual = atual[:-1].rstrip()
        feitos.append("barra_final")
    if valido(atual):
        return (atual, feitos) if feitos else (linha, [])
    m = PADRAO.match(atual)
    if m:
        s = re.sub(r'(?<!\\)"', r'\\"', m.group("s"))
        tentativa = f'{{"sentence":"{s}","relations":{m.group("r")}}}'
        if valido(tentativa):
            return tentativa, feitos + ["aspas_na_sentenca"]
    return linha, []                                    # sem correção segura


def processar(caminho: Path, aplicar: bool) -> dict:
    texto = caminho.read_text(encoding="utf-8")
    linhas = texto.split("\n")
    candidatas = [l for l in linhas if l.strip()]
    if not candidatas or sum(l.startswith(ABRE) for l in candidatas) < 0.9 * len(candidatas):
        return {"ignorado": True}
    novas, cont, restantes = [], {}, []
    for i, l in enumerate(linhas, 1):
        if l.startswith(ABRE):
            nova, feitos = corrigir_linha(l)
            for d in feitos:
                cont[d] = cont.get(d, 0) + 1
            if not feitos and not valido(l.rstrip("\r")):
                restantes.append(i)
            novas.append(nova)
        else:
            novas.append(l)
    mudou = novas != linhas
    if mudou and aplicar:
        bak = caminho.with_name(caminho.name + ".pre_correcao.bak")
        if not bak.exists():
            bak.write_text(texto, encoding="utf-8", newline="")
        caminho.write_text("\n".join(novas), encoding="utf-8", newline="")
    return {"ignorado": False, "linhas": len(candidatas), "corrigidos": cont, "mudou": mudou,
            "ainda_invalidas": restantes}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aplicar", action="store_true", help="grava as correções (padrão: só relatório)")
    ap.add_argument("--raiz", default="Respostas", help="pasta a varrer (padrão: Respostas)")
    args = ap.parse_args()

    base = (RAIZ / args.raiz) if not Path(args.raiz).is_absolute() else Path(args.raiz)
    arquivos = sorted(p for p in base.rglob("*.jsonl")
                      if "backup" not in str(p).lower() and "_bruto" not in p.parts)
    alterados = pendentes = 0
    for p in arquivos:
        r = processar(p, args.aplicar)
        if r["ignorado"] or (not r["mudou"] and not r["ainda_invalidas"]):
            continue
        rel = p.relative_to(RAIZ)
        print(f"{rel}\n   linhas={r['linhas']}  corrigidas={r['corrigidos']}")
        if r["ainda_invalidas"]:
            pendentes += 1
            print(f"   AINDA INVÁLIDAS (linhas {r['ainda_invalidas'][:15]}{'...' if len(r['ainda_invalidas']) > 15 else ''})")
        alterados += bool(r["mudou"])
    modo = "gravados" if args.aplicar else "seriam alterados (rode com --aplicar para gravar)"
    print(f"\n{alterados} arquivo(s) {modo}; {pendentes} com linhas que precisam de correção manual.")


if __name__ == "__main__":
    main()
