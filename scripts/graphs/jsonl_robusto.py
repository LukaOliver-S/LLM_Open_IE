"""Leitura tolerante de JSON/JSONL gerado por LLMs.

Aceita: JSONL de uma linha por objeto, array JSON, objetos em várias linhas,
cercas de código Markdown e vírgulas penduradas antes de ] ou }.
Listas de listas (um bloco por frase) são achatadas em uma lista plana.
"""
import json
import re
from pathlib import Path

_CERCA = re.compile(r"^```[a-zA-Z]*\s*|\s*```$", re.MULTILINE)
_VIRGULA = re.compile(r",\s*([\]}])")


def _achatar(itens):
    saida = []
    for item in itens:
        if isinstance(item, list):
            saida.extend(_achatar(item))
        else:
            saida.append(item)
    return saida


def carregar_objetos(caminho):
    """Devolve (objetos, erros). Cada erro é um texto curto para diagnóstico."""
    texto = Path(caminho).read_text(encoding="utf-8", errors="replace").strip()
    texto = _VIRGULA.sub(r"\1", _CERCA.sub("", texto).strip())

    if texto.startswith("[") and texto.endswith("]"):
        try:
            return _achatar(json.loads(texto)), []
        except json.JSONDecodeError:
            pass

    objetos, erros = [], []
    decoder = json.JSONDecoder()
    i, n = 0, len(texto)
    while i < n:
        while i < n and texto[i] in " \n\r\t,[]":
            i += 1
        if i >= n:
            break
        try:
            obj, fim = decoder.raw_decode(texto, i)
            objetos.append(obj)
            i = fim
        except json.JSONDecodeError:
            erros.append(f"{Path(caminho).name}: JSON inválido perto do offset {i}: {texto[i:i + 60]!r}")
            proximo = texto.find("{", i + 1)
            if proximo == -1:
                break
            i = proximo
    return _achatar(objetos), erros
