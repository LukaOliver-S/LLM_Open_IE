"""
checagem_consenso.py
=====================
Para os falsos positivos de cada modelo, verifica quantos OUTROS modelos
(independentemente) propuseram uma tripla equivalente para a mesma frase.
Concordância entre modelos independentes é evidência indireta de que o gold
perdeu uma relação real, sem precisar julgar "certo/errado" por conta própria
-- é só uma medida observacional de concordância.

Uso: `python checagem_consenso.py`, de dentro de `scripts/Validacao/`, com o
cwd na raiz do projeto (mesma convenção dos outros scripts).
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List

import pandas as pd
import matplotlib.pyplot as plt

from resultados import (
    log,
    RobustJSONLReader,
    achatar_predicoes,
    extrair_triplas,
    Triple,
    LexicalMatcher,
    _normalizar_sentenca,
)
parser = argparse.ArgumentParser()
parser.add_argument("--lotes", type=int, default=None,
                        help="Processar só este tamanho de lote (ex.: 25). Se omitido, processa todos.")
args = parser.parse_args()

def triplas_falsos_positivos(gold_triplas: List[Triple], pred_triplas: List[Triple], matcher: LexicalMatcher) -> List[Triple]:
    """Mesma lógica gulosa 1-para-1 de `comparar_triplas`, devolvendo as
    triplas PREDITAS que não casaram com nenhum gold (falsos positivos)."""
    usadas: set = set()
    falsos_positivos = []
    for p in pred_triplas:
        achou = False
        for i, g in enumerate(gold_triplas):
            if i not in usadas and matcher.bate(g, p):
                usadas.add(i)
                achou = True
                break
        if not achou:
            falsos_positivos.append(p)
    return falsos_positivos

def deduplicar_triplas(triplas: List[Triple], matcher: LexicalMatcher) -> List[Triple]:
    """Colapsa triplas quase-idênticas do MESMO modelo/frase em uma só
    representante -- evita que decomposição/verbosidade infle artificialmente
    as chances de 'concordância' com outros modelos."""
    canonicas: List[Triple] = []
    for t in triplas:
        if not any(matcher.bate(t, c) for c in canonicas):
            canonicas.append(t)
    return canonicas

def coletar_fp_por_sentenca(caminho_gold: str, pasta_categoria: Path, limiar_lexical: float = 0.5):
    """Para cada modelo em `pasta_categoria`, calcula os falsos positivos por
    sentença. Retorna {chave_sentenca: {modelo: [Triple, ...]}} e o texto
    original de cada sentença."""
    golds = RobustJSONLReader(Path(caminho_gold)).carregar().objetos
    gold_por_sentenca = {_normalizar_sentenca(g.get("sentence", "")): g for g in golds}
    matcher = LexicalMatcher(limiar=limiar_lexical)

    fp_por_sentenca: Dict[str, Dict[str, List[Triple]]] = {}
    sentenca_texto: Dict[str, str] = {}

    for arquivo in sorted(pasta_categoria.glob("*.jsonl")):
        modelo = arquivo.stem
        preds = achatar_predicoes(RobustJSONLReader(arquivo).carregar().objetos)
        for item_pred in preds:
            sentenca = item_pred.get("sentence", "") if isinstance(item_pred, dict) else ""
            chave = _normalizar_sentenca(sentenca)
            item_gold = gold_por_sentenca.get(chave)
            if item_gold is None:
                continue
            gold_triplas = extrair_triplas(item_gold)
            pred_triplas = extrair_triplas(item_pred)
            fps = triplas_falsos_positivos(gold_triplas, pred_triplas, matcher)
            fps = deduplicar_triplas(fps, matcher)
            fp_por_sentenca.setdefault(chave, {})[modelo] = fps
            sentenca_texto[chave] = sentenca

    return fp_por_sentenca, sentenca_texto


def calcular_consenso(fp_por_sentenca, sentenca_texto, limiar_lexical: float = 0.5):
    matcher = LexicalMatcher(limiar=limiar_lexical)
    contagem_modelo: Dict[str, Dict[str, int]] = {}
    fortes: List[dict] = []

    for chave, por_modelo in fp_por_sentenca.items():
        modelos_da_frase = list(por_modelo.keys())
        for modelo, triplas in por_modelo.items():
            c = contagem_modelo.setdefault(modelo, {"total_fp": 0, "com_consenso": 0})
            for t in triplas:
                c["total_fp"] += 1
                n_concordam = sum(
                    1 for outro in modelos_da_frase
                    if outro != modelo and any(matcher.bate(t, ot) for ot in por_modelo[outro])
                )
                if n_concordam >= 1:
                    c["com_consenso"] += 1
                if n_concordam >= 2:
                    fortes.append({
                        "sentence": sentenca_texto[chave],
                        "modelo_exemplo": modelo,
                        "arg1": t.arg1, "rel": t.rel, "arg2": t.arg2,
                        "n_modelos_concordando": n_concordam + 1,
                    })

    resumo = pd.DataFrame([
        {
            "modelo": modelo,
            "total_falsos_positivos": c["total_fp"],
            "com_consenso_de_outro_modelo": c["com_consenso"],
            "pct_com_consenso": (c["com_consenso"] / c["total_fp"] * 100) if c["total_fp"] else 0.0,
        }
        for modelo, c in contagem_modelo.items()
    ])
    detalhe_forte = pd.DataFrame(fortes).drop_duplicates() if fortes else pd.DataFrame()
    return resumo, detalhe_forte


def plotar_consenso(df: pd.DataFrame, caminho_png: Path) -> None:
    d = df.sort_values("pct_com_consenso", ascending=False).copy()
    d["pct_isolado"] = 100 - d["pct_com_consenso"]

    fig, ax = plt.subplots(figsize=(max(7, 0.8 * len(d)), 5))
    x = range(len(d))
    ax.bar(x, d["pct_com_consenso"], label="Outro(s) modelo(s) concordam", color="#2980b9")
    ax.bar(x, d["pct_isolado"], bottom=d["pct_com_consenso"], label="Isolado (nenhum outro modelo)", color="#95a5a6")
    ax.set_xticks(list(x))
    ax.set_xticklabels(d["modelo"], rotation=30, ha="right")
    ax.set_ylabel("% dos falsos positivos")
    ax.set_title("Concordância entre modelos nos falsos positivos")
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(caminho_png, dpi=150)
    plt.close(fig)


def main() -> None:
    gold = "dados/bia_gold_sentences.jsonl"
    raiz_respostas = Path("Respostas")
    raiz_metricas = Path("Outputs") / "metricas"

    lotes = sorted(p for p in raiz_respostas.iterdir() if p.is_dir() and p.name.endswith("_batches"))
    if args.lotes is not None:
        lotes = [p for p in lotes if p.name == f"{args.lotes}_batches"]
    if not lotes:
        raise FileNotFoundError(f"Pasta 'Respostas/{args.lotes}_batches' não encontrada.")
    for lote in lotes:
        pastas = sorted(p for p in lote.iterdir() if p.is_dir() and p.name.startswith("Respostas"))
        if not pastas:
            continue

        for pasta in pastas:
            log.info("=== Consenso: %s/%s ===", lote.name, pasta.name)
            try:
                fp_por_sentenca, sentenca_texto = coletar_fp_por_sentenca(gold, pasta)
                resumo, detalhe_forte = calcular_consenso(fp_por_sentenca, sentenca_texto)
            except Exception as e:
                log.error("Falha ao processar '%s/%s': %s", lote.name, pasta.name, e)
                continue

            nome_base = pasta.name.replace(" ", "_")
            pasta_saida = raiz_metricas / lote.name / "consenso"
            pasta_saida.mkdir(parents=True, exist_ok=True)

            resumo.to_csv(pasta_saida / f"resumo_consenso_{nome_base}.csv", index=False)
            plotar_consenso(resumo, pasta_saida / f"consenso_{nome_base}.png")
            if not detalhe_forte.empty:
                detalhe_forte.to_csv(pasta_saida / f"consenso_forte_{nome_base}.csv", index=False)

            log.info("Resultados salvos em %s", pasta_saida)


if __name__ == "__main__":
    main()