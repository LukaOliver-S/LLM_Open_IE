"""
resultados_por_batch.py
========================
Quebra a avaliação de resultados.py por lote de envio (batch) em vez de
agregar tudo em um único número por modelo. Reaproveita toda a lógica de
leitura/matching/triplas de `resultados.py` — só muda o agrupamento final.

Uso: `python resultados_por_batch.py` (sem argumentos). Varre as mesmas
pastas `Respostas/<N>_batches/Respostas *` que o modo padrão de
`resultados.py`, usando `sentencas/<N>_sentencas/sentencas_parte_*.jsonl`
para saber a qual lote cada frase pertence.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict

import pandas as pd
import matplotlib.pyplot as plt

from scripts.Validacao.resultados import (
    log,
    RobustJSONLReader,
    achatar_predicoes,
    extrair_triplas,
    comparar_triplas,
    LexicalMatcher,
    ExactMatcher,
    Contadores,
    _normalizar_sentenca,
)

_RE_PARTE = re.compile(r"sentencas_parte_(\d+)\.jsonl$")


def carregar_mapa_sentenca_batch(pasta_sentencas: Path) -> Dict[str, int]:
    """Lê `sentencas/<N>_sentencas/sentencas_parte_*.jsonl` e devolve um
    mapa {sentença normalizada -> número do lote}."""
    mapa: Dict[str, int] = {}
    for arquivo in sorted(pasta_sentencas.glob("sentencas_parte_*.jsonl")):
        m = _RE_PARTE.search(arquivo.name)
        if not m:
            continue
        lote = int(m.group(1))
        itens = RobustJSONLReader(arquivo).carregar().objetos
        for item in itens:
            if isinstance(item, dict):
                chave = _normalizar_sentenca(item.get("sentence", ""))
                mapa[chave] = lote
    return mapa


def avaliar_por_batch(
    caminho_gold: str,
    caminho_pred: str,
    mapa_sentenca_batch: Dict[str, int],
    limiar_lexical: float = 0.5,
) -> pd.DataFrame:
    """Mesma lógica de casamento por sentença de `avaliar_par`, mas agregando
    os contadores (vp/fp/fn) por número de lote em vez de um total único."""
    nome_modelo = Path(caminho_pred).stem

    golds = RobustJSONLReader(Path(caminho_gold)).carregar().objetos
    preds = achatar_predicoes(RobustJSONLReader(Path(caminho_pred)).carregar().objetos)

    gold_por_sentenca = {
        _normalizar_sentenca(g.get("sentence", "") if isinstance(g, dict) else ""): g
        for g in golds
    }

    matcher_lex = LexicalMatcher(limiar=limiar_lexical)
    matcher_ex = ExactMatcher()

    contadores_lex: Dict[int, Contadores] = {}
    contadores_ex: Dict[int, Contadores] = {}
    pareadas: set = set()

    def _contador(mapa: Dict[int, Contadores], lote: int) -> Contadores:
        if lote not in mapa:
            mapa[lote] = Contadores()
        return mapa[lote]

    for item_pred in preds:
        chave = _normalizar_sentenca(item_pred.get("sentence", "") if isinstance(item_pred, dict) else "")
        item_gold = gold_por_sentenca.get(chave)
        lote = mapa_sentenca_batch.get(chave)
        if item_gold is None or lote is None:
            continue  # sentença fora do gold ou sem lote conhecido

        pareadas.add(chave)
        gold_triplas = extrair_triplas(item_gold)
        pred_triplas = extrair_triplas(item_pred)

        r_lex = comparar_triplas(gold_triplas, pred_triplas, matcher_lex)
        r_ex = comparar_triplas(gold_triplas, pred_triplas, matcher_ex)

        c_lex = _contador(contadores_lex, lote)
        c_ex = _contador(contadores_ex, lote)
        c_lex.vp += r_lex.vp; c_lex.fp += r_lex.fp; c_lex.fn += r_lex.fn
        c_ex.vp += r_ex.vp; c_ex.fp += r_ex.fp; c_ex.fn += r_ex.fn

    # Sentenças do gold nunca cobertas: penaliza recall no lote a que pertencem
    for chave, item_gold in gold_por_sentenca.items():
        if chave in pareadas:
            continue
        lote = mapa_sentenca_batch.get(chave)
        if lote is None:
            continue
        gold_triplas = extrair_triplas(item_gold)
        c_lex = _contador(contadores_lex, lote)
        c_ex = _contador(contadores_ex, lote)
        c_lex.fn += len(gold_triplas)
        c_ex.fn += len(gold_triplas)

    linhas = []
    for lote in sorted(set(contadores_lex) | set(contadores_ex)):
        c_lex = contadores_lex.get(lote, Contadores())
        c_ex = contadores_ex.get(lote, Contadores())
        linhas.append({
            "modelo": nome_modelo,
            "batch": lote,
            "precisao_lexical": c_lex.precisao(),
            "recall_lexical": c_lex.recall(),
            "f1_lexical": c_lex.f1(),
            "precisao_exact": c_ex.precisao(),
            "recall_exact": c_ex.recall(),
            "f1_exact": c_ex.f1(),
        })
    return pd.DataFrame(linhas)


def avaliar_diretorio_por_batch(
    caminho_gold: str, diretorio_pred: str, mapa_sentenca_batch: Dict[str, int], limiar_lexical: float = 0.5
) -> pd.DataFrame:
    arquivos = sorted(Path(diretorio_pred).glob("*.jsonl"))
    partes = [
        avaliar_por_batch(caminho_gold, str(f), mapa_sentenca_batch, limiar_lexical)
        for f in arquivos
    ]
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


def plotar_f1_por_batch(df: pd.DataFrame, titulo: str, caminho_png: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))
    for modelo, grupo in df.groupby("modelo"):
        grupo = grupo.sort_values("batch")
        ax.plot(grupo["batch"], grupo["f1_lexical"], marker="o", label=modelo)
    ax.set_xlabel("Lote (batch)")
    ax.set_ylabel("F1 lexical")
    ax.set_title(titulo)
    ax.set_xticks(sorted(df["batch"].unique()))
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(caminho_png, dpi=150)
    plt.close(fig)


def main() -> None:
    gold = "dados/bia_gold_sentences.jsonl"
    raiz_respostas = Path("Respostas")
    raiz_metricas = Path("Outputs") / "metricas"

    lotes_pastas = sorted(p for p in raiz_respostas.iterdir() if p.is_dir() and p.name.endswith("_batches"))
    for lote_pasta in lotes_pastas:
        n = lote_pasta.name.split("_")[0]
        pasta_sentencas = Path("sentencas") / f"{n}_sentencas"
        if not pasta_sentencas.is_dir():
            log.warning("Pasta de lotes '%s' não encontrada para '%s'; pulando.", pasta_sentencas, lote_pasta.name)
            continue
        mapa_batch = carregar_mapa_sentenca_batch(pasta_sentencas)

        pasta_saida = raiz_metricas / lote_pasta.name / "por_batch"
        pasta_saida.mkdir(parents=True, exist_ok=True)

        for pasta_categoria in sorted(p for p in lote_pasta.iterdir() if p.is_dir() and p.name.startswith("Respostas")):
            log.info("=== Por batch: %s/%s ===", lote_pasta.name, pasta_categoria.name)
            df = avaliar_diretorio_por_batch(gold, str(pasta_categoria), mapa_batch)
            if df.empty:
                log.warning("Sem dados para '%s'.", pasta_categoria.name)
                continue

            nome_base = pasta_categoria.name.replace(" ", "_")
            csv_path = pasta_saida / f"resultados_batch_{nome_base}.csv"
            df.sort_values(["modelo", "batch"]).to_csv(csv_path, index=False)
            log.info("CSV salvo em %s", csv_path)

            png_path = pasta_saida / f"grafico_f1_lexical_{nome_base}.png"
            plotar_f1_por_batch(df, f"F1 lexical por lote — {pasta_categoria.name}", png_path)
            log.info("Gráfico salvo em %s", png_path)


if __name__ == "__main__":
    main()