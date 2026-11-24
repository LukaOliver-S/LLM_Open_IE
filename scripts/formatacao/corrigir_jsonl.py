"""Corrige defeitos de formato em respostas .jsonl (uma sentença por linha) sem mexer no conteúdo.

Defeitos tratados (só em linhas que começam com {"sentence"):
  barra_final        `\\` solto no fim da linha (vem da cópia do chat)               -> removida
  barra_dupla        `\\"` (escape duplicado) dentro de textos                        -> vira `\\"` correto
  aspas_sem_escape   aspas internas sem escape em "sentence", "arg1", "rel" ou "arg2" -> escapadas
  objetos_juntos     dois ou mais registros na mesma linha (`}]}{"sentence":...`)     -> separados em linhas
  texto_extra        texto solto depois do JSON (ex.: "FIM")                           -> descartado
Arquivos que não são de uma linha por sentença (JSON indentado em várias linhas) são ignorados.
Linhas que continuam inválidas depois da correção ficam como estavam e são listadas.
O conteúdo das triplas e das sentenças não é alterado, só a pontuação/estrutura do JSON.

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
INICIO = re.compile(r'^\{\s*"sentence"\s*:\s*"')     # aceita `{"sentence":"` e `{"sentence": "`
FRAGMENTO = re.compile(r'^\s*"?arg1"\s*:.*\}\s*\]\s*\}\s*$')   # ex.: `arg1": "TASS", "rel": ..., "arg2": ...}]}`

# Marcas estruturais (aspas que fazem parte da sintaxe JSON). Todas as outras aspas são conteúdo.
# Todas toleram espaços ao redor de `:` e `,`, pois alguns arquivos não são compactos.
MARCAS = [
    re.compile(r'"\s*\}(?=\s*,\s*\{|\s*\])'),   # fim de tripla: vem primeiro, pois olha o `{` seguinte, que outra marca consumiria
    re.compile(r'\{\s*"sentence"\s*:\s*"'),
    re.compile(r'"\s*,\s*"relations"\s*:\s*\['),
    re.compile(r'\{\s*"arg1"\s*:\s*"'),
    re.compile(r'"\s*,\s*"rel"\s*:\s*"'),
    re.compile(r'"\s*,\s*"arg2"\s*:\s*"'),
]


def valido(linha: str) -> bool:
    try:
        json.loads(linha)
        return True
    except Exception:
        return False


def separar_objetos(texto: str) -> tuple[list[dict], str] | None:
    """Lê objetos JSON consecutivos. Devolve (objetos, resto_nao_json) ou None se não achar nenhum."""
    dec, pos, objs = json.JSONDecoder(), 0, []
    while pos < len(texto):
        while pos < len(texto) and texto[pos].isspace():
            pos += 1
        if pos >= len(texto):
            break
        try:
            obj, fim = dec.raw_decode(texto, pos)
        except Exception:
            break
        if not isinstance(obj, dict) or "sentence" not in obj:
            break
        objs.append(obj)
        pos = fim
    return (objs, texto[pos:].strip()) if objs else None


def escapar_aspas_internas(texto: str) -> str:
    guardado: list[str] = []

    def guardar(m: re.Match) -> str:
        guardado.append(m.group(0))
        return f"\x01{len(guardado) - 1}\x02"

    for marca in MARCAS:
        texto = marca.sub(guardar, texto)
    texto = texto.replace('"', '\\"')
    return re.sub(r"\x01(\d+)\x02", lambda m: guardado[int(m.group(1))], texto)


def corrigir_linha(linha: str) -> tuple[list[str], list[str]]:
    """Devolve (linhas_resultantes, defeitos_corrigidos). Sem correção segura: ([linha], [])."""
    feitos: list[str] = []
    atual = linha.rstrip("\r\n ")
    if valido(atual):
        return [linha], []
    if atual.endswith("\\"):
        atual = atual[:-1].rstrip()
        feitos.append("barra_final")
    def aceitavel(a) -> bool:                       # leu tudo, ou sobrou só uma palavra solta curta
        return a is not None and (not a[1] or (len(a[1]) <= 20 and not a[1].startswith(("{", "["))))

    achado = separar_objetos(atual)
    if not aceitavel(achado):
        reparado = atual
        extras: list[str] = []
        if '\\\\"' in reparado:
            reparado = reparado.replace('\\\\"', '"')
            extras.append("barra_dupla")
        if '"]}' in reparado:                        # tripla sem a `}` que a fecha: ..."arg2":""]}
            reparado = reparado.replace('"]}', '"}]}')
            extras.append("chave_faltando")
        reparado = escapar_aspas_internas(reparado) if '"' in reparado else reparado
        achado = separar_objetos(reparado)
        if not aceitavel(achado):
            return [linha], []                      # sem correção segura: não toca na linha
        feitos += extras + ["aspas_sem_escape"]
    objs, resto = achado
    if resto:
        feitos.append("texto_extra")
    if len(objs) > 1:
        feitos.append("objetos_juntos")
    saida = [json.dumps(o, ensure_ascii=False, separators=(",", ":")) for o in objs]
    return saida, feitos


def processar(caminho: Path, aplicar: bool) -> dict:
    texto = caminho.read_text(encoding="utf-8")
    linhas = texto.split("\n")
    candidatas = [l for l in linhas if l.strip()]
    if not candidatas or sum(bool(INICIO.match(l)) for l in candidatas) < 0.9 * len(candidatas):
        return {"ignorado": True}
    novas, cont, restantes = [], {}, []
    for i, l in enumerate(linhas, 1):
        if INICIO.match(l):
            res, feitos = corrigir_linha(l)
            for d in feitos:
                cont[d] = cont.get(d, 0) + 1
            if not feitos and not valido(l.rstrip("\r")):
                restantes.append(i)
            novas.extend(res)
        elif FRAGMENTO.match(l):                            # resto de objeto sem o início: descartado
            cont["fragmento_orfao"] = cont.get("fragmento_orfao", 0) + 1
        else:
            novas.append(l)
    n_depois = sum(1 for l in novas if l.strip())
    mudou = novas != linhas
    if mudou and aplicar:
        bak = caminho.with_name(caminho.name + ".pre_correcao.bak")
        if not bak.exists():
            bak.write_text(texto, encoding="utf-8", newline="")
        caminho.write_text("\n".join(novas), encoding="utf-8", newline="")
    return {"ignorado": False, "linhas": len(candidatas), "linhas_depois": n_depois, "corrigidos": cont,
            "mudou": mudou, "ainda_invalidas": restantes}


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
        print(f"{p.relative_to(RAIZ)}\n   linhas {r['linhas']} -> {r['linhas_depois']}  corrigidas={r['corrigidos']}")
        if r["ainda_invalidas"]:
            pendentes += 1
            print(f"   AINDA INVÁLIDAS (linhas {r['ainda_invalidas'][:15]}{'...' if len(r['ainda_invalidas']) > 15 else ''})")
        alterados += bool(r["mudou"])
    modo = "gravados" if args.aplicar else "seriam alterados (rode com --aplicar para gravar)"
    print(f"\n{alterados} arquivo(s) {modo}; {pendentes} com linhas que precisam de correção manual.")


if __name__ == "__main__":
    main()
