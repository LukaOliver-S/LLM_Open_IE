import json
import os
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
from matplotlib.patches import Polygon

NAVY = "#01195e"
COR_GOLD = "#2e7d32"
COR_ARESTA = "#d35400"  # laranja, contrasta com qualquer cor de nó e deixa a seta visível
PALETA = ["#01195e", "#17a2a0", "#e07b00", "#8e3b9d", "#c0392b", "#5d6d7e"]


def _quebrar(texto, largura):
    return "\n".join(textwrap.wrap(texto, largura)) or texto


def _posicoes(G):
    """Layout por componente conexo. Cada componente ganha uma célula de grade
    grande o bastante para o maior deles, assim triplas desconectadas não se
    sobrepõem nem se espalham, e sobra linha visível entre as caixas."""
    componentes = sorted((list(c) for c in nx.weakly_connected_components(G)), key=len, reverse=True)
    locais = []
    for nos in componentes:
        if len(nos) == 1:
            local = {nos[0]: (0.0, 0.0)}
        elif len(nos) == 2:
            local = {nos[0]: (-1.5, 0.0), nos[1]: (1.5, 0.0)}
        else:
            local = nx.spring_layout(nx.Graph(G.subgraph(nos)), seed=7, k=2.0, iterations=300, scale=1.8)
        fator = min(1.5 + 0.16 * max(len(nos) - 3, 0), 2.8) if len(nos) >= 3 else 1.0   # componentes grandes precisam de mais espaço
        local = {n: (x * 1.9 * fator, y * 1.5 * fator) for n, (x, y) in local.items()}
        xs, ys = [p[0] for p in local.values()], [p[1] for p in local.values()]
        locais.append((local, (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, max(xs) - min(xs), max(ys) - min(ys)))
    celula_larg = max(l[3] for l in locais) + 5.5   # 5.5 = folga para as caixas de texto
    celula_alt = max(l[4] for l in locais) + 3.4
    colunas = max(1, int(len(locais) ** 0.5 + 0.999))
    pos = {}
    for k, (local, mx, my, _, _) in enumerate(locais):
        cx, cy = (k % colunas) * celula_larg, -(k // colunas) * celula_alt
        for n, (x, y) in local.items():
            pos[n] = (cx + x - mx, cy + y - my)
    return pos


def _desenhar(ax, triplas, cor, titulo):
    """Desenha caixas e linhas. As setas e os rótulos são adicionados depois em
    `_finalizar`, quando o tamanho real das caixas já é conhecido."""
    G = nx.MultiDiGraph()
    for a1, rel, a2 in triplas:
        G.add_edge(a1, a2, rel=rel)
    ax.set_title(f"{titulo} ({len(triplas)} {'tripla' if len(triplas) == 1 else 'triplas'})",
                 fontsize=11, color=NAVY, fontweight="bold")
    ax.axis("off")
    ax._pendentes = []
    if G.number_of_edges() == 0:
        ax.text(0.5, 0.5, "sem triplas", ha="center", va="center", color="#888888", transform=ax.transAxes)
        return
    pos = _posicoes(G)
    caixas = {
        n: ax.text(x, y, _quebrar(n, 20), ha="center", va="center", fontsize=7.2, color="white", zorder=3,
                   bbox=dict(boxstyle="round,pad=0.35", fc=cor, ec=cor))
        for n, (x, y) in pos.items()
    }
    paralelas = {}
    for u, v, dados in G.edges(data=True):
        i = paralelas.get((u, v), 0)
        paralelas[(u, v)] = i + 1
        rad = 0.18 + 0.22 * i
        (x1, y1), (x2, y2) = pos[u], pos[v]
        # a linha, a ponta e o rótulo são desenhados em _finalizar
        ax._pendentes.append((u, v, rad, dados["rel"], pos, caixas))
    xs, ys = [p[0] for p in pos.values()], [p[1] for p in pos.values()]
    ax.set_xlim(min(xs) - 2.4, max(xs) + 2.4)
    ax.set_ylim(min(ys) - 1.6, max(ys) + 1.6)
    ax.set_aspect("equal", adjustable="box")


def _finalizar(fig, axes):
    """Coloca a seta e o rótulo no meio do trecho VISÍVEL de cada linha, isto é,
    fora das duas caixas. Assim a direção nunca fica escondida atrás de uma caixa."""
    fig.canvas.draw()
    for ax in axes:
        pendentes = getattr(ax, "_pendentes", [])
        if not pendentes:
            continue
        para_dados = ax.transData.inverted()
        (qx0, _), (qx1, _) = para_dados.transform([(0, 0), (1, 0)])
        un_por_px = abs(qx1 - qx0)  # unidades de dados por pixel neste painel

        def retangulo(caixa):
            e = caixa.get_bbox_patch().get_window_extent()
            (xa, ya), (xb, yb) = para_dados.transform([(e.x0, e.y0), (e.x1, e.y1)])
            return xa, ya, xb, yb

        for u, v, rad, rel, pos, caixas in pendentes:
            (x1, y1), (x2, y2) = pos[u], pos[v]
            dx, dy = x2 - x1, y2 - y1
            cx, cy = (x1 + x2) / 2 + rad * dy, (y1 + y2) / 2 - rad * dx  # ponto de controle do arc3

            def ponto(t):
                a, b, c = (1 - t) ** 2, 2 * t * (1 - t), t ** 2
                return a * x1 + b * cx + c * x2, a * y1 + b * cy + c * y2

            ru, rv = retangulo(caixas[u]), retangulo(caixas[v])

            def dentro(p, r, m=0.0):
                return r[0] - m <= p[0] <= r[2] + m and r[1] - m <= p[1] <= r[3] + m

            ts = [i / 200 for i in range(201)]
            visiveis = [t for t in ts if not dentro(ponto(t), ru) and not dentro(ponto(t), rv)]
            if len(visiveis) >= 2:
                lin = [ponto(x) for x in ts if visiveis[0] <= x <= visiveis[-1]]
                ax.plot([q[0] for q in lin], [q[1] for q in lin], color=COR_ARESTA, lw=1.8, zorder=2,
                        solid_capstyle="butt")
            t_meio = (visiveis[0] + visiveis[-1]) / 2 if visiveis else 0.5
            px, py = ponto(t_meio)
            ax_, ay_ = ponto(max(t_meio - 0.01, 0.0))
            bx_, by_ = ponto(min(t_meio + 0.01, 1.0))
            tx, ty = bx_ - ax_, by_ - ay_
            norma = (tx ** 2 + ty ** 2) ** 0.5 or 1.0
            tx, ty = tx / norma, ty / norma          # tangente unitária, de arg1 para arg2
            nx_, ny_ = -ty, tx                        # normal unitária
            comp, larg = 9 * un_por_px, 6.5 * un_por_px   # ponta com tamanho fixo em pixels
            ponta = Polygon([(px + tx * comp, py + ty * comp),
                             (px - tx * comp + nx_ * larg, py - ty * comp + ny_ * larg),
                             (px - tx * comp - nx_ * larg, py - ty * comp - ny_ * larg)],
                            closed=True, fc=COR_ARESTA, ec=COR_ARESTA, zorder=4)
            ax.add_patch(ponta)
            if ny_ < 0 or (abs(ny_) < 1e-6 and nx_ < 0):   # rótulo sempre do lado de cima
                nx_, ny_ = -nx_, -ny_
            rotulo = _quebrar(rel, 18)
            meia_larg = 2.9 * max(len(l) for l in rotulo.split("\n")) + 5   # em pixels, estimativa
            meia_alt = 5.5 * (rotulo.count("\n") + 1) + 3
            afastar = (abs(nx_) * meia_larg + abs(ny_) * meia_alt + 12) * un_por_px
            ax.text(px + nx_ * afastar, py + ny_ * afastar, rotulo, fontsize=6.6, color=NAVY,
                    ha="center", va="center", zorder=5,
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec=COR_ARESTA, lw=0.8))


class GraphPlotter:
    def __init__(self, output_dir):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def plot_triplas(self, paineis, frase, graph_name):
        """Um PNG com um painel por extrator. `paineis` é uma lista de
        (nome, [(arg1, rel, arg2), ...]). Um painel chamado 'gold' fica verde."""
        n = len(paineis)
        colunas = min(n, 2)
        linhas = (n + colunas - 1) // colunas
        fig, axes = plt.subplots(linhas, colunas, figsize=(9 * colunas, 6.2 * linhas), squeeze=False)
        proxima = 0
        for i, (nome, triplas) in enumerate(paineis):
            if nome.lower() == "gold":
                cor = COR_GOLD
            else:
                cor = PALETA[proxima % len(PALETA)]
                proxima += 1
            _desenhar(axes[i // colunas][i % colunas], triplas, cor, nome)
        for j in range(n, linhas * colunas):
            axes[j // colunas][j % colunas].axis("off")
        if frase:
            fig.suptitle(_quebrar(frase, 140), fontsize=11, color=NAVY)
        fig.tight_layout()
        _finalizar(fig, [ax for linha in axes for ax in linha])
        fig.text(0.5, -0.005, "Seta laranja: do arg1 (origem) para o arg2 (ponta). O texto sobre a seta é a rel.",
                 ha="center", va="top", fontsize=9, color=COR_ARESTA)
        caminho = os.path.join(self.output_dir, f"{graph_name}.png")
        fig.savefig(caminho, dpi=170, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        return caminho

    def plot_graph(self, graph_data, graph_name):
        """Desenha um grafo no formato node-link (os JSON do GraphCreator)."""
        if "nodes" not in graph_data and isinstance(graph_data.get("graph"), dict):
            graph_data = graph_data["graph"]
        if "nodes" not in graph_data:
            raise ValueError(f"{graph_name} is not a valid NetworkX graph JSON. Expected a 'nodes' field.")
        edge_key = "edges" if "edges" in graph_data else "links"
        G = nx.node_link_graph(graph_data, edges=edge_key)
        triplas = [(u, d.get("rel", ""), v) for u, v, d in G.edges(data=True)]
        return self.plot_triplas([(graph_name, triplas)], G.graph.get("sentence", ""), graph_name)

    def plot_jsonl(self, input_file):
        base = os.path.splitext(os.path.basename(input_file))[0]
        with open(input_file, "r", encoding="utf-8") as f:
            for line_number, line in enumerate(f, start=1):
                if not line.strip():
                    continue
                try:
                    graph_data = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f"Invalid JSON in {input_file} at line {line_number}") from error
                self.plot_graph(graph_data, f"{base}_line_{line_number}")
