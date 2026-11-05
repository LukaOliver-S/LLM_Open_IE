import json
import os
import re

import networkx as nx

from jsonl_robusto import carregar_objetos


def normalizar(frase):
    """Chave de casamento entre arquivos: espaços colapsados e minúsculas."""
    return " ".join(str(frase or "").split()).strip().lower()


def ler_triplas(item, fonte="auto"):
    """Extrai (frase, [(arg1, rel, arg2), ...]) de um objeto.

    fonte: "auto" usa `gold` se existir, senão `relations` ou `triples`.
           Também aceita "gold", "relations" ou "triples" para forçar uma chave.
    Relações com valid=false, sem arg1 ou sem arg2 são ignoradas, e duplicatas
    exatas são removidas mantendo a ordem.
    """
    if not isinstance(item, dict):
        return "", []
    chaves = ("gold", "relations", "triples") if fonte == "auto" else (fonte,)
    relacoes = next((item[c] for c in chaves if isinstance(item.get(c), list)), [])
    triplas, vistas = [], set()
    for r in relacoes:
        if not isinstance(r, dict) or r.get("valid", True) is False:
            continue
        t = tuple(str(r.get(c, "") or "").strip() for c in ("arg1", "rel", "arg2"))
        if t[0] and t[2] and t not in vistas:
            vistas.add(t)
            triplas.append(t)
    return str(item.get("sentence", "")).strip(), triplas


def ler_arquivo(caminho, fonte="auto"):
    """Devolve (lista de (frase, triplas), erros), na ordem do arquivo."""
    objetos, erros = carregar_objetos(caminho)
    frases = [ler_triplas(o, fonte) for o in objetos if isinstance(o, dict)]
    return frases, erros


class GraphCreator:
    def __init__(self, output_dir, triples_archive, fonte="auto"):
        self.output_dir = output_dir
        self.triples_archive = triples_archive
        self.fonte = fonte
        os.makedirs(self.output_dir, exist_ok=True)

    def create_graph(self, nodes, edges, graph_name, output_format: str = "json", frase=""):
        G = nx.MultiDiGraph(sentence=frase)
        G.add_nodes_from(nodes)
        G.add_edges_from(edges)

        if output_format == "json":
            return self._save_graph_as_json(G, graph_name)
        if output_format == "graphml":
            return self._save_graph_as_graphml(G, graph_name)
        raise ValueError(f"Formato desconhecido: {output_format!r} (use 'json' ou 'graphml')")

    def _save_graph_as_json(self, G, graph_name):
        caminho = os.path.join(self.output_dir, f"{graph_name}.json")
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(nx.node_link_data(G, edges="edges"), f, indent=4, ensure_ascii=False)
        return caminho

    def _save_graph_as_graphml(self, G, graph_name):
        caminho = os.path.join(self.output_dir, f"{graph_name}.graphml")
        nx.write_graphml(G, caminho)
        return caminho

    def _arquivos_de_entrada(self):
        if os.path.isfile(self.triples_archive):
            return [self.triples_archive]
        if os.path.isdir(self.triples_archive):
            return sorted(
                os.path.join(self.triples_archive, nome)
                for nome in os.listdir(self.triples_archive)
                if nome.endswith((".json", ".jsonl"))
            )
        raise FileNotFoundError(f"Input path does not exist: {self.triples_archive}")

    def triple_to_graph(self, sentencas=None, output_format="json"):
        """Cria um grafo por frase. `sentencas` é um conjunto de índices (a partir
        de 0) para gerar só algumas frases, ou None para todas. Devolve os caminhos
        gravados. Frases sem nenhuma tripla válida não geram arquivo."""
        gravados = []
        for caminho in self._arquivos_de_entrada():
            nome_arquivo = os.path.splitext(os.path.basename(caminho))[0]
            frases, erros = ler_arquivo(caminho, self.fonte)
            for erro in erros:
                print("aviso:", erro)
            for indice, (frase, triplas) in enumerate(frases):
                if sentencas is not None and indice not in sentencas:
                    continue
                if not triplas:
                    continue
                nos = {n for a1, _, a2 in triplas for n in (a1, a2)}
                arestas = [(a1, a2, {"rel": rel}) for a1, rel, a2 in triplas]
                gravados.append(
                    self.create_graph(nos, arestas, f"{nome_arquivo}_{indice:03d}", output_format, frase)
                )
        return gravados
