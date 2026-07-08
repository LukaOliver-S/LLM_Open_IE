#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
corrigir_gemini.py
===================

Conserta arquivos de predição do Gemini (ou qualquer LLM que faça a mesma
coisa) que vieram no formato ERRADO para o pipeline de avaliação.

O QUE O GEMINI FEZ DE DIFERENTE
---------------------------------
O `resultados.py` espera, para cada frase, um item assim:

    {"sentence": "...", "relations": [{"arg1":..., "rel":..., "arg2":...}, ...]}

Mas o Gemini devolveu uma lista ACHATADA: cada tripla é um item separado,
com o texto da frase repetido dentro dela:

    {"sentence": "...", "arg1": "...", "rel": "...", "arg2": "..."}
    {"sentence": "...", "arg1": "...", "rel": "...", "arg2": "..."}  <- mesma frase, tripla diferente
    ...

E, para piorar, o arquivo tem VÁRIOS blocos `[ ... ]` colados um atrás do
outro (às vezes com cercas ```json), como se fossem várias respostas da
LLM concatenadas — inclusive com blocos quase idênticos repetidos
(retries).

O QUE ESSE SCRIPT FAZ
-----------------------
1. Lê o arquivo bruto e extrai TODOS os objetos/arrays JSON válidos,
   não importa quantos blocos `[...]` existam ou se há cercas Markdown.
2. Achata tudo em uma lista única de triplas soltas.
3. Agrupa as triplas por frase (usando o texto normalizado da frase
   como chave), na ordem de primeira aparição.
4. Remove triplas EXATAMENTE duplicadas (mesmo arg1/rel/arg2) que
   apareceram por causa dos blocos repetidos.
5. Escreve um novo arquivo `.jsonl` no formato agrupado esperado pelo
   `resultados.py` (uma lista JSON de objetos "sentence" + "relations").

USO
----
    python3 corrigir_gemini.py entrada.jsonl saida_corrigida.jsonl

Se você não passar o segundo argumento, o script cria automaticamente
"<nome_original>_corrigido.jsonl" na mesma pasta.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List


# --------------------------------------------------------------------------- #
# 1. LEITURA ROBUSTA (mesma técnica do resultados.py: raw_decode incremental)
# --------------------------------------------------------------------------- #

_RE_MARKDOWN_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$", re.MULTILINE)


def ler_todos_os_objetos_json(caminho: Path) -> List[Any]:
    """Extrai todo objeto/array JSON válido do arquivo, ignorando cercas
    de Markdown e o que estiver entre um bloco e outro (espaços, vírgulas,
    quebras de linha)."""
    texto = caminho.read_text(encoding="utf-8", errors="replace").strip()
    texto = _RE_MARKDOWN_FENCE.sub("", texto).strip()

    objetos: List[Any] = []
    decoder = json.JSONDecoder()
    idx = 0
    n = len(texto)
    erros = 0

    while idx < n:
        while idx < n and texto[idx] in " \n\r\t,":
            idx += 1
        if idx >= n:
            break
        try:
            obj, fim = decoder.raw_decode(texto, idx)
            objetos.append(obj)
            idx = fim
        except json.JSONDecodeError:
            trecho = texto[idx: idx + 60].replace("\n", "\\n")
            print(f"⚠️  Trecho ignorado (JSON inválido) no offset {idx}: '{trecho}...'")
            erros += 1
            idx += 1

    if erros:
        print(f"⚠️  Total de {erros} trecho(s) ignorado(s) por erro de sintaxe.")
    return objetos


def achatar(objetos: List[Any]) -> List[Any]:
    """Achata blocos [ ... ][ ... ] em uma única lista de itens."""
    achatado = []
    for obj in objetos:
        if isinstance(obj, list):
            achatado.extend(obj)
        else:
            achatado.append(obj)
    return achatado


# --------------------------------------------------------------------------- #
# 2. AGRUPAMENTO POR FRASE + DEDUPLICAÇÃO
# --------------------------------------------------------------------------- #

_RE_ESPACOS = re.compile(r"\s+")


def normalizar_frase(s: str) -> str:
    s = (s or "").strip().lower()
    s = _RE_ESPACOS.sub(" ", s)
    return s.strip(" .:;,-")


def agrupar_por_frase(itens: List[Any]) -> "list[dict]":
    """Agrupa triplas soltas (cada uma com 'sentence' embutida) por frase,
    preservando a ORDEM de primeira aparição e removendo triplas
    exatamente duplicadas (mesmo arg1/rel/arg2) dentro da mesma frase.
    """
    ordem_frases: List[str] = []
    frase_original: Dict[str, str] = {}
    triplas_por_frase: Dict[str, List[Dict[str, str]]] = {}
    assinaturas_vistas: Dict[str, set] = {}
    frases_com_bloco_repetido = 0

    for item in itens:
        if not isinstance(item, dict):
            continue

        frase_bruta = item.get("sentence", "")
        chave = normalizar_frase(frase_bruta)
        if not chave:
            continue  # item sem frase associada -> não dá para agrupar, descarta com aviso

        if chave not in triplas_por_frase:
            ordem_frases.append(chave)
            frase_original[chave] = frase_bruta
            triplas_por_frase[chave] = []
            assinaturas_vistas[chave] = set()

        arg1 = str(item.get("arg1", "") or "")
        rel = str(item.get("rel", item.get("relation", "")) or "")
        arg2 = str(item.get("arg2", "") or "")

        # Se o item não é uma tripla "achatada" (não tem arg1/rel/arg2 diretos),
        # talvez já venha agrupado (lista sob 'gold'/'triples'/'relations') — trata os dois casos.
        sub_listas = None
        for chave_lista in ("gold", "triples", "relations"):
            if chave_lista in item and isinstance(item[chave_lista], list):
                sub_listas = item[chave_lista]
                break

        candidatas = sub_listas if sub_listas is not None else [
            {"arg1": arg1, "rel": rel, "arg2": arg2}
        ]

        for t in candidatas:
            if not isinstance(t, dict):
                continue
            a1 = str(t.get("arg1", "") or "")
            r = str(t.get("rel", t.get("relation", "")) or "")
            a2 = str(t.get("arg2", "") or "")
            if not (a1 or r or a2):
                continue
            assinatura = (normalizar_frase(a1), normalizar_frase(r), normalizar_frase(a2))
            if assinatura in assinaturas_vistas[chave]:
                continue
            assinaturas_vistas[chave].add(assinatura)
            triplas_por_frase[chave].append({"arg1": a1, "rel": r, "arg2": a2})

    resultado = [
        {
            "sentence": frase_original[chave],
            "relations": triplas_por_frase[chave],
        }
        for chave in ordem_frases
    ]
    return resultado


# --------------------------------------------------------------------------- #
# 3. CLI
# --------------------------------------------------------------------------- #

def main():
    if len(sys.argv) < 2:
        print("Uso: python3 corrigir_gemini.py entrada.jsonl [saida_corrigida.jsonl]")
        sys.exit(1)

    caminho_entrada = Path(sys.argv[1])
    if not caminho_entrada.exists():
        print(f"❌ Arquivo não encontrado: {caminho_entrada}")
        sys.exit(1)

    if len(sys.argv) >= 3:
        caminho_saida = Path(sys.argv[2])
    else:
        caminho_saida = caminho_entrada.with_name(caminho_entrada.stem + "_corrigido.jsonl")

    print(f"Lendo: {caminho_entrada} ...")
    objetos = ler_todos_os_objetos_json(caminho_entrada)
    itens = achatar(objetos)
    print(f"-> {len(itens)} item(ns) bruto(s) encontrado(s) (triplas soltas + eventuais blocos já agrupados).")

    agrupado = agrupar_por_frase(itens)
    total_triplas = sum(len(x["relations"]) for x in agrupado)
    print(f"-> Agrupado em {len(agrupado)} frase(s) únicas, totalizando {total_triplas} tripla(s) (após deduplicação).")

    with open(caminho_saida, "w", encoding="utf-8") as f:
        json.dump(agrupado, f, ensure_ascii=False, indent=2)

    print(f"✅ Arquivo corrigido salvo em: {caminho_saida}")
    print("   Use esse arquivo no lugar do original com --pred (ou dentro da pasta usada em --pred-dir).")


if __name__ == "__main__":
    main()