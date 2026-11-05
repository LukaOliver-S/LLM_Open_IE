"""Gera grafos (arg1 --rel--> arg2) a partir de arquivos de extrações ou de gold.

Dois modos:
  "comparar"   um PNG por frase com um painel por entrada (gold e extratores lado a lado)
  "individual" um grafo por frase e por entrada, exportado em JSON ou GraphML e desenhado

Organização da saída (nada é sobrescrito entre comparações diferentes):
  Outputs/graphs/comparacao/<corpus>/<gold_x_Claude_x_Grok>/frase_000.png
  Outputs/graphs/comparacao/<corpus>/<gold_x_Claude_x_Grok>/LEIAME.txt   (entradas usadas)
  Outputs/graphs/individual/<corpus>/<nome-da-entrada>/json_graphs/*.json
  Outputs/graphs/individual/<corpus>/<nome-da-entrada>/plots/*.png

Edite a seção CONFIGURAÇÃO abaixo e rode `python run_graph.py`, ou sobrescreva
qualquer valor pela linha de comando (veja `python run_graph.py --help`).
"""
import argparse
import datetime
import json
import re
from pathlib import Path

from graph_creator import GraphCreator, ler_arquivo, normalizar
from graph_plot import GraphPlotter

BASE_DIR = Path(__file__).resolve().parent.parents[1]
RESPOSTAS = BASE_DIR / "Respostas" / "oiec_pt" / "10_batches" / "Respostas ExtrativoOIEC-PT"

# ============================== CONFIGURAÇÃO ==============================
# Cada entrada é um caminho, ou um par (nome, caminho) para dar nome ao painel.
# A primeira entrada define a ordem e os índices das frases. As demais são
# casadas com ela pelo texto da frase. O nome "gold" pinta o painel de verde.
ENTRADAS = [
    ("gold", BASE_DIR / "dados" / "oiec_pt_gold_sentences.jsonl"),
    ("Grok", RESPOSTAS / "Grok4.0Fast.jsonl"),
    ("Claude", RESPOSTAS / "Claude_Sonnet5.jsonl"),
]
CORPUS = "oiec_pt"           # vira uma subpasta (ex.: oiec_pt, bia). Use "" para não criar
NOME_COMPARACAO = None       # None = automático a partir das entradas (gold_x_Grok_x_Claude)
MODO = "comparar"            # "comparar" ou "individual"
SENTENCAS = [0, 1, 2]        # índices a partir de 0, ou None para todas as frases
FONTE = "auto"               # "auto" (gold, senão relations ou triples), "gold", "relations" ou "triples"
FORMATO_EXPORT = "json"      # "json" ou "graphml" (só no modo "individual")
SAIDA = BASE_DIR / "Outputs" / "graphs"
# ===========================================================================


def _slug(texto):
    """Nome seguro para pasta: troca o que não é letra, número, '.' ou '-' por '_'."""
    return re.sub(r"[^\w.-]+", "_", str(texto)).strip("_") or "sem_nome"


def _parse_sentencas(texto):
    """'0,3,5-8' vira {0, 3, 5, 6, 7, 8}. 'todas' vira None."""
    if texto.strip().lower() == "todas":
        return None
    indices = set()
    for parte in texto.split(","):
        if "-" in parte:
            a, b = parte.split("-")
            indices.update(range(int(a), int(b) + 1))
        elif parte.strip():
            indices.add(int(parte))
    return indices


def _parse_entrada(texto):
    """'nome=caminho' ou só 'caminho'."""
    if "=" in texto and not Path(texto).exists():
        nome, caminho = texto.split("=", 1)
        return nome, Path(caminho)
    return Path(texto).stem, Path(texto)


def _normaliza_entradas(entradas):
    return [e if isinstance(e, tuple) else (Path(e).stem, Path(e)) for e in entradas]


def _pasta_base(saida, tipo, corpus):
    return saida / tipo / _slug(corpus) if corpus else saida / tipo


def _escrever_leiame(destino, entradas, modo, fonte, sentencas):
    linhas = [
        f"Gerado em {datetime.datetime.now():%Y-%m-%d %H:%M}",
        f"Modo: {modo}   Fonte das triplas: {fonte}",
        f"Frases: {'todas' if sentencas is None else sorted(sentencas)}",
        "Entradas (a primeira define os índices das frases):",
    ]
    linhas += [f"  {nome}: {caminho}" for nome, caminho in entradas]
    (destino / "LEIAME.txt").write_text("\n".join(linhas) + "\n", encoding="utf-8")


def modo_comparar(entradas, sentencas, fonte, destino):
    dados = []
    for nome, caminho in entradas:
        frases, erros = ler_arquivo(caminho, fonte)
        for erro in erros:
            print("aviso:", erro)
        dados.append((nome, {normalizar(f): t for f, t in frases}, frases))
    referencia = dados[0][2]
    indices = range(len(referencia)) if sentencas is None else sorted(sentencas)
    plotter = GraphPlotter(destino)
    for i in indices:
        if not 0 <= i < len(referencia):
            print(f"aviso: índice {i} fora do intervalo 0..{len(referencia) - 1}")
            continue
        frase = referencia[i][0]
        paineis = [(nome, por_frase.get(normalizar(frase), [])) for nome, por_frase, _ in dados]
        print("ok", plotter.plot_triplas(paineis, f"[{i}] {frase}", f"frase_{i:03d}"))
    _escrever_leiame(Path(destino), entradas, "comparar", fonte, sentencas)


def modo_individual(entradas, sentencas, fonte, formato, destino_base):
    for nome, caminho in entradas:
        pasta = Path(destino_base) / _slug(nome)
        criador = GraphCreator(pasta / "json_graphs", caminho, fonte)
        plotter = GraphPlotter(pasta / "plots")
        for arquivo in criador.triple_to_graph(sentencas, formato):
            if arquivo.endswith(".json"):
                dados = json.loads(Path(arquivo).read_text(encoding="utf-8"))
                print("ok", plotter.plot_graph(dados, Path(arquivo).stem))
            else:
                print("ok", arquivo)
        _escrever_leiame(pasta, [(nome, caminho)], "individual", fonte, sentencas)


def main():
    ap = argparse.ArgumentParser(description="Grafos de triplas. Sem argumentos usa a CONFIGURAÇÃO do arquivo.")
    ap.add_argument("--entrada", action="append", help="caminho ou nome=caminho (repita para várias entradas)")
    ap.add_argument("--modo", choices=["comparar", "individual"])
    ap.add_argument("--sentencas", help="ex.: 0,3,5-8 ou todas")
    ap.add_argument("--fonte", choices=["auto", "gold", "relations", "triples"])
    ap.add_argument("--formato", choices=["json", "graphml"])
    ap.add_argument("--corpus", help="subpasta do corpus (ex.: oiec_pt, bia). Vazio para não criar")
    ap.add_argument("--nome", help="nome da pasta da comparação (padrão: gold_x_Claude_x_...)")
    ap.add_argument("--saida", type=Path)
    a = ap.parse_args()

    entradas = [_parse_entrada(e) for e in a.entrada] if a.entrada else _normaliza_entradas(ENTRADAS)
    modo = a.modo or MODO
    sentencas = _parse_sentencas(a.sentencas) if a.sentencas else (None if SENTENCAS is None else set(SENTENCAS))
    fonte = a.fonte or FONTE
    formato = a.formato or FORMATO_EXPORT
    saida = a.saida or SAIDA
    corpus = CORPUS if a.corpus is None else a.corpus

    if modo == "comparar":
        nome = _slug(a.nome or NOME_COMPARACAO or "_x_".join(_slug(n) for n, _ in entradas))
        destino = _pasta_base(saida, "comparacao", corpus) / nome
        modo_comparar(entradas, sentencas, fonte, destino)
    else:
        destino = _pasta_base(saida, "individual", corpus)
        modo_individual(entradas, sentencas, fonte, formato, destino)
    print(f"Pronto. Saída em {destino}")


if __name__ == "__main__":
    main()
