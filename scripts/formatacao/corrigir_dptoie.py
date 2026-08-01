#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
corrigir_dptoie.py
==================

Conserta o arquivo de predição do DptOIE (DPTOIE-PY) para bater com o gold,
no mesmo espírito do `corrigir_gemini.py`.

O QUE O DptOIE FAZ DE DIFERENTE
-------------------------------
O DptOIE re-tokeniza a frase: expande contrações que o gold mantém
contraídas e mexe em hífens/espaços de pontuação:

    gold:      "Na primavera ... pelos estudiosos ... Pode-se dizer"
    DPTOIE-PY: "Em a primavera ... por os estudiosos ... Pode se dizer"

É a MESMA frase, escrita diferente. Como o `resultados.py` casa
predição<->gold pelo TEXTO da frase, essas frases não casam e o modelo
leva zeros indevidos (era isso que derrubava o F1 do DPTOIE-PY).

O QUE ESSE SCRIPT FAZ
---------------------
1. Lê o arquivo do DPTOIE-PY (formato {"sentence","relations"}), de forma
   robusta (aceita jsonl e array JSON).
2. Casa cada frase do gold com a predição usando uma normalização robusta
   a contrações; se o casamento exato falhar, usa similaridade (fuzzy) como
   fallback.
3. Substitui o texto da frase pelo texto EXATO do gold. As TRIPLAS ficam
   intactas (é a saída real do modelo — não "ajudamos" o modelo).
4. Reordena/completa para bater a ordem e a quantidade do gold (frases sem
   predição entram com relations=[]).
5. Escreve um novo .jsonl corrigido, SEM tocar no arquivo original.

USO
----
    python3 corrigir_dptoie.py entrada.jsonl [saida_corrigida.jsonl] --gold dados/bia_gold_sentences.jsonl

Se você não passar o segundo argumento, cria "<nome>_corrigido.jsonl".
O --gold é obrigatório aqui (o conserto é justamente alinhar ao gold).
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Tuple

# --------------------------------------------------------------------------- #
# 1. NORMALIZAÇÃO ROBUSTA A CONTRAÇÕES (só para CASAR frases; simétrica)
# --------------------------------------------------------------------------- #
# Expande as contrações preposição+artigo/determinante para uma forma canônica
# comum. Aplicada IGUAL ao gold e à predição, então não favorece ninguém:
# só faz duas grafias da MESMA frase colapsarem na mesma chave.
_CONTRACOES = {
    # de + ...
    "do": "de o", "da": "de a", "dos": "de os", "das": "de as",
    "dum": "de um", "duma": "de uma", "duns": "de uns", "dumas": "de umas",
    "dele": "de ele", "dela": "de ela", "deles": "de eles", "delas": "de elas",
    "deste": "de este", "desta": "de esta", "destes": "de estes", "destas": "de estas", "disto": "de isto",
    "desse": "de esse", "dessa": "de essa", "desses": "de esses", "dessas": "de essas", "disso": "de isso",
    "daquele": "de aquele", "daquela": "de aquela", "daqueles": "de aqueles", "daquelas": "de aquelas", "daquilo": "de aquilo",
    "daqui": "de aqui", "dali": "de ali", "daí": "de aí",
    # em + ...
    "no": "em o", "na": "em a", "nos": "em os", "nas": "em as",
    "num": "em um", "numa": "em uma", "nuns": "em uns", "numas": "em umas",
    "nele": "em ele", "nela": "em ela", "neles": "em eles", "nelas": "em elas",
    "neste": "em este", "nesta": "em esta", "nestes": "em estes", "nestas": "em estas", "nisto": "em isto",
    "nesse": "em esse", "nessa": "em essa", "nesses": "em esses", "nessas": "em essas", "nisso": "em isso",
    "naquele": "em aquele", "naquela": "em aquela", "naqueles": "em aqueles", "naquelas": "em aquelas", "naquilo": "em aquilo",
    # a + ... (crase)
    "ao": "a o", "à": "a a", "aos": "a os", "às": "a as",
    "àquele": "a aquele", "àquela": "a aquela", "àqueles": "a aqueles", "àquelas": "a aquelas", "àquilo": "a aquilo",
    # por + ... (pel-)
    "pelo": "por o", "pela": "por a", "pelos": "por os", "pelas": "por as",
}
_RE_CONTRACOES = re.compile(
    r"\b(" + "|".join(sorted(_CONTRACOES, key=len, reverse=True)) + r")\b", re.UNICODE
)


def norm(s: Any) -> str:
    """Chave de casamento: minúsculas -> expande contrações -> remove acentos
    -> remove espaços/hífens/pontuação. Duas grafias da mesma frase caem na
    mesma string."""
    s = str(s or "").lower()
    s = _RE_CONTRACOES.sub(lambda m: _CONTRACOES[m.group(0)], s)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^0-9a-z]", "", s)


# --------------------------------------------------------------------------- #
# 2. LEITURA ROBUSTA (aceita jsonl OU array JSON, com ou sem cercas markdown)
# --------------------------------------------------------------------------- #
_RE_MARKDOWN_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$", re.MULTILINE)


def carregar_itens(caminho: Path) -> List[dict]:
    """Extrai todos os objetos {"sentence","relations"} do arquivo, seja ele
    jsonl (um por linha) ou um array JSON inteiro."""
    texto = _RE_MARKDOWN_FENCE.sub("", caminho.read_text(encoding="utf-8", errors="replace")).strip()
    itens: List[Any] = []
    decoder = json.JSONDecoder()
    idx, n = 0, len(texto)
    while idx < n:
        while idx < n and texto[idx] in " \n\r\t,":
            idx += 1
        if idx >= n:
            break
        try:
            obj, fim = decoder.raw_decode(texto, idx)
            itens.append(obj)
            idx = fim
        except json.JSONDecodeError:
            idx += 1
    # achata eventuais blocos [ ... ]
    achatado: List[dict] = []
    for obj in itens:
        if isinstance(obj, list):
            achatado.extend(x for x in obj if isinstance(x, dict))
        elif isinstance(obj, dict):
            achatado.append(obj)
    return achatado


def carregar_frases_gold(caminho_gold: Path) -> List[str]:
    """Lê o gold e devolve as frases (texto original) NA ORDEM em que aparecem."""
    return [it["sentence"] for it in carregar_itens(caminho_gold)
            if isinstance(it, dict) and "sentence" in it]


# --------------------------------------------------------------------------- #
# 3. ALINHAMENTO AO GOLD (exato por chave normalizada + fallback fuzzy)
# --------------------------------------------------------------------------- #

def alinhar_ao_gold(
    preds: List[dict], frases_gold: List[str], limiar_fuzzy: float = 0.90
) -> Tuple[List[dict], int, int, int]:
    """Para cada frase do gold, acha a predição correspondente (casamento
    exato pela chave normalizada; se falhar, a predição mais parecida acima
    de `limiar_fuzzy`) e devolve a lista alinhada com o TEXTO EXATO do gold e
    as TRIPLAS do modelo. Frases sem predição entram com relations=[]."""
    pred_por_chave: Dict[str, dict] = {}
    for r in preds:
        if isinstance(r, dict) and "sentence" in r:
            pred_por_chave.setdefault(norm(r["sentence"]), r)
    preds_norm = [(norm(r["sentence"]), r) for r in preds
                  if isinstance(r, dict) and "sentence" in r]

    usados: set = set()
    saida: List[dict] = []
    n_exato = n_fuzzy = n_faltando = 0

    for frase in frases_gold:
        gk = norm(frase)
        r = pred_por_chave.get(gk)
        if r is not None and id(r) not in usados:
            usados.add(id(r))
            n_exato += 1
            saida.append({"sentence": frase, "relations": r.get("relations", [])})
            continue
        # fallback fuzzy: melhor predição ainda não usada
        melhor_ratio, melhor_r = 0.0, None
        for pk, pr in preds_norm:
            if id(pr) in usados:
                continue
            ratio = SequenceMatcher(None, gk, pk).ratio()
            if ratio > melhor_ratio:
                melhor_ratio, melhor_r = ratio, pr
        if melhor_r is not None and melhor_ratio >= limiar_fuzzy:
            usados.add(id(melhor_r))
            n_fuzzy += 1
            saida.append({"sentence": frase, "relations": melhor_r.get("relations", [])})
        else:
            n_faltando += 1
            saida.append({"sentence": frase, "relations": []})

    return saida, n_exato, n_fuzzy, n_faltando


# --------------------------------------------------------------------------- #
# 4. CLI
# --------------------------------------------------------------------------- #

def main():
    args = sys.argv[1:]
    if not args or "--gold" not in args:
        print("Uso: python3 corrigir_dptoie.py entrada.jsonl [saida.jsonl] --gold dados/bia_gold_sentences.jsonl")
        sys.exit(1)

    idx_gold = args.index("--gold")
    caminho_gold = Path(args[idx_gold + 1])
    del args[idx_gold: idx_gold + 2]

    caminho_entrada = Path(args[0])
    caminho_saida = Path(args[1]) if len(args) >= 2 else \
        caminho_entrada.with_name(caminho_entrada.stem + "_corrigido.jsonl")

    for p in (caminho_entrada, caminho_gold):
        if not p.exists():
            print(f"❌ Arquivo não encontrado: {p}")
            sys.exit(1)

    print(f"Lendo predição: {caminho_entrada}")
    preds = carregar_itens(caminho_entrada)
    frases_gold = carregar_frases_gold(caminho_gold)
    print(f"-> {len(preds)} frase(s) na predição | {len(frases_gold)} frase(s) no gold")

    saida, n_exato, n_fuzzy, n_faltando = alinhar_ao_gold(preds, frases_gold)
    print(f"-> casadas exato={n_exato} | casadas fuzzy={n_fuzzy} | sem predição (relations=[])={n_faltando}")

    with open(caminho_saida, "w", encoding="utf-8") as f:
        for item in saida:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"✅ Arquivo corrigido salvo em: {caminho_saida}")
    print("   Use-o no lugar do original (dentro da pasta usada no --pred-dir / modo padrão).")


if __name__ == "__main__":
    main()
