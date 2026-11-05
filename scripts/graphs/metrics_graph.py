# -*- coding: utf-8 -*-
"""Métricas de grafos (as da aula) sobre extrações de Open IE em JSONL.

Entrada: arquivos .jsonl com {"sentence": "...", "relations": [{"arg1": ..., "rel": ..., "arg2": ...}]}
Saída:   metricas_corpus.csv     (uma linha por arquivo: o grafo de todas as sentenças juntas)
         metricas_sentencas.csv  (uma linha por arquivo e sentença: o grafo de cada sentença)

Uso: python metricas_grafos.py arq1.jsonl arq2.jsonl --saida pasta_saida
"""
import argparse
import csv
import json
import random
import statistics as st
from itertools import combinations
from pathlib import Path

import networkx as nx
# ============================== CONFIGURAÇÃO ==============================
DADOS = Path(r"C:\Users\User\Documents\IC_FORMAS\raw\TASKS\TASK-1\Codes\LLM_Open_IE")   # pasta com dados/, Respostas/ e Outputs/
SAIDA_PADRAO = Path(r"C:\Users\User\Documents\IC_FORMAS\raw\TASKS\TASK-1\LLM_Open_IE\Outputs") / "graphs" / "metrics"
CORPORA = ("oiec_pt", "bia", "unified")
# ==========================================================================


def inferir_corpus(p):
    """acha o corpus pelo nome de uma pasta do caminho ou pelo início do nome do arquivo (bia_gold_..., oiec_pt_gold_...)"""
    for parte in [x.lower() for x in p.resolve().parts] + [p.stem.lower()]:
        for c in CORPORA:
            if parte == c or parte.startswith(c + "_"):
                return c
    return "outros"


def inferir_grupo(p, corpus_nome):
    """gold -> 'gold'. Extrações -> caminho depois da pasta do corpus, por exemplo 10_batches/k2/Respostas ExtrativoOIEC-PT"""
    if "gold" in p.stem.lower():
        return "gold"
    pasta = p if p.is_dir() else p.parent
    partes = list(pasta.resolve().parts)
    baixo = [x.lower() for x in partes]
    if corpus_nome in baixo:
        return "/".join(partes[baixo.index(corpus_nome) + 1:]) or "geral"
    return pasta.name


def tarefas(corpora, tipos):
    """lista (corpus, grupo, arquivos) com tudo o que existe em DADOS: os gold e cada pasta de extrações"""
    out = []
    if "gold" in tipos:
        for c in corpora:
            f = DADOS / "dados" / f"{c}_gold_sentences.jsonl"
            if f.exists():
                out.append((c, "gold", [f]))
    if "extracoes" in tipos:
        for c in corpora:
            base = DADOS / "Respostas" / c
            if not base.exists():
                continue
            for pasta in sorted({f.parent for f in base.rglob("*.jsonl")}):
                partes = pasta.relative_to(base).parts
                if any(x.startswith("_") for x in partes):      # ignora _bruto e _extratores_locais
                    continue
                out.append((c, "/".join(partes) or "geral", sorted(pasta.glob("*.jsonl"))))
    return out


def processar(arquivos, corpus_nome, grupo, saida):
    destino = saida / corpus_nome / grupo
    destino.mkdir(parents=True, exist_ok=True)
    print(f"\n== {corpus_nome} / {grupo}")
    linhas_corpus, linhas_sent = [], []
    for arq in arquivos:
        D, sem_triplas, total = nx.DiGraph(), 0, 0
        for idx, (frase, rels) in enumerate(ler_jsonl(arq)):
            total += 1
            Ds = construir(rels)
            if Ds.number_of_edges() == 0:
                sem_triplas += 1
                continue
            D = nx.compose(D, Ds)
            linhas_sent.append({"arquivo": arq.stem, "sentenca": idx, "triplas": len(rels), **por_sentenca(Ds.to_undirected())})
        if D.number_of_edges() == 0:
            print("sem triplas em", arq.name)
            continue
        linhas_corpus.append({"arquivo": arq.stem, "sentencas": total, "sentencas_sem_triplas": sem_triplas, **corpus(D)})
    gravar(destino / "metricas_corpus.csv", linhas_corpus)
    gravar(destino / "metricas_sentencas.csv", linhas_sent)
    for arq in dict.fromkeys(l["arquivo"] for l in linhas_sent):
        ls = [l for l in linhas_sent if l["arquivo"] == arq]
        formatos = {f: sum(1 for l in ls if l["formato"] == f) / len(ls) for f in ("estrela", "arvore", "com ciclo", "desconexo")}
        print(f"{arq}: {len(ls)} sentenças | n médio {st.mean(l['n'] for l in ls):.2f} | m médio {st.mean(l['m'] for l in ls):.2f} | "
              + " | ".join(f"{k} {v:.1%}" for k, v in formatos.items()))



def norm(t):
    """minúsculas e espaços normalizados, para 'O enxofre' e 'o enxofre' virarem o mesmo vértice"""
    return " ".join(str(t).lower().split()) if t is not None else ""
def ler_jsonl(caminho):
    """lê JSONL (um objeto por linha) ou arrays JSON indentados, um depois do outro. Gold usa 'gold', extrações usam 'relations'"""
    texto = Path(caminho).read_text(encoding="utf-8")
    dec, pos, n, itens, invalidos = json.JSONDecoder(), 0, len(texto), [], 0
    while True:                                  # lê objetos e arrays JSON em sequência, em uma ou várias linhas
        while pos < n and texto[pos].isspace():
            pos += 1
        if pos >= n:
            break
        try:
            obj, pos = dec.raw_decode(texto, pos)
        except json.JSONDecodeError:
            invalidos += 1                       # trecho inválido: pula até a próxima linha e continua
            prox = texto.find("\n", pos)
            if prox == -1:
                break
            pos = prox + 1
            continue
        itens.extend(obj if isinstance(obj, list) else [obj])
    if invalidos:
        print(f"aviso: {invalidos} trecho(s) inválido(s) em {Path(caminho).name}, ignorados")
    for obj in itens:
        if not isinstance(obj, dict):
            continue
        rels = obj.get("relations")
        if rels is None:                         # arquivo de gold: usa só as triplas válidas
            rels = [r for r in (obj.get("gold") or []) if isinstance(r, dict) and r.get("valid", True) is not False]
        yield obj.get("sentence", ""), rels or []

def construir(relacoes):
    """cada tripla (arg1, rel, arg2) vira uma aresta arg1 -> arg2. Laços e triplas incompletas são descartados"""
    D = nx.DiGraph()
    for r in relacoes:
        if not isinstance(r, dict):
            continue
        a, b, rel = norm(r.get("arg1")), norm(r.get("arg2")), norm(r.get("rel"))
        if a and b and a != b:
            D.add_edge(a, b, rel=rel)
    return D


def cobertura_minima(G, limite=18):
    """tau exato por força bruta, só para grafos pequenos (cobertura de vértices é NP-difícil)"""
    if G.number_of_nodes() > limite:
        return None
    nos, arestas = list(G), list(G.edges())
    for k in range(len(nos) + 1):
        for S in combinations(nos, k):
            S = set(S)
            if all(u in S or v in S for u, v in arestas):
                return k


def formato(G):
    """classifica o formato do grafo de uma sentença"""
    n, m = G.number_of_nodes(), G.number_of_edges()
    if not nx.is_connected(G):
        return "desconexo"
    if n >= 3 and m == n - 1 and max(d for _, d in G.degree()) == n - 1:
        return "estrela"
    if m == n - 1:
        return "arvore"
    return "com ciclo"


def por_sentenca(G):
    n, m = G.number_of_nodes(), G.number_of_edges()
    graus = [d for _, d in G.degree()]
    nu = len(nx.max_weight_matching(G, maxcardinality=True))      # emparelhamento máximo
    tau = cobertura_minima(G)                                     # cobertura de vértices mínima
    conexo = nx.is_connected(G)
    return {
        "n": n, "m": m, "grau_max": max(graus), "componentes": nx.number_connected_components(G),
        "conexo": conexo, "formato": formato(G),
        "pontes": sum(1 for _ in nx.bridges(G)), "articulacoes": sum(1 for _ in nx.articulation_points(G)),
        "diametro": nx.diameter(G) if conexo else "",
        "triangulos": sum(nx.triangles(G).values()) // 3,
        "nu": nu, "tau": tau if tau is not None else "",
        "alfa": n - tau if tau is not None else "",               # Gallai: alfa + tau = n
        "rho": n - nu,                                            # Gallai: nu + rho = n (sem vértice isolado)
    }


def top(dic, k=5):
    return "; ".join(f"{v} ({x:.3g})" for v, x in sorted(dic.items(), key=lambda t: -t[1])[:k])


def corpus(D, semente=0):
    """métricas do grafo de todas as sentenças juntas. Betweenness e diâmetro usam amostragem se o grafo for grande"""
    G = D.to_undirected()
    n, m = G.number_of_nodes(), G.number_of_edges()
    comps = sorted(nx.connected_components(G), key=len, reverse=True)
    maior = G.subgraph(comps[0])
    graus = [d for _, d in G.degree()]
    rnd = random.Random(semente)
    if maior.number_of_nodes() <= 1500:
        diam, rotulo_diam = nx.diameter(maior), "exato"
    else:
        amostra = rnd.sample(list(maior), 100)
        diam, rotulo_diam = max(max(nx.single_source_shortest_path_length(maior, v).values()) for v in amostra), "limite inferior"
    k = min(300, n)
    inter = nx.betweenness_centrality(G, k=k, seed=semente, normalized=True)
    prox = nx.closeness_centrality(maior) if maior.number_of_nodes() <= 5000 else {}
    nu = len(nx.max_weight_matching(G, maxcardinality=True))
    return {
        "n": n, "m": m, "densidade": round(nx.density(G), 6), "componentes": len(comps),
        "maior_componente": len(comps[0]), "fracao_maior": round(len(comps[0]) / n, 4),
        "grau_medio": round(sum(graus) / n, 3), "grau_max": max(graus),
        "pontes": sum(1 for _ in nx.bridges(G)), "articulacoes": sum(1 for _ in nx.articulation_points(G)),
        "diametro_maior_comp": diam, "diametro_tipo": rotulo_diam,
        "agrupamento_medio": round(nx.average_clustering(G), 4), "transitividade": round(nx.transitivity(G), 4),
        "nu": nu, "tau_min_possivel": nu, "tau_max_garantido": 2 * nu,   # nu <= tau <= 2 nu
        "alfa_min_garantido": n - 2 * nu, "alfa_max_possivel": n - nu,   # Gallai: alfa = n - tau
        "top_grau": top(dict(G.degree()), 5),
        "top_intermediacao": top(inter, 5) + f"  [amostra de {k} vértices]",
        "top_proximidade": top(prox, 5) if prox else "",
    }


def gravar(caminho, linhas):
    if not linhas:
        return
    campos = list(dict.fromkeys(c for l in linhas for c in l))
    with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(linhas)
    print("gravado:", caminho)




def main():
    ap = argparse.ArgumentParser(description="Métricas de grafos dos corpora (gold) e das extrações.")
    ap.add_argument("alvos", nargs="*", help="gold, extracoes, bia, oiec_pt, unified (combináveis). Sem nada = tudo. "
                    "Também aceita caminhos de .jsonl ou de pastas")
    ap.add_argument("--saida", type=Path, default=SAIDA_PADRAO, help=f"padrão: {SAIDA_PADRAO}")
    a = ap.parse_args()

    caminhos = [Path(x) for x in a.alvos if Path(x).exists()]
    palavras = {x.lower() for x in a.alvos if not Path(x).exists()}
    desconhecidas = palavras - set(CORPORA) - {"gold", "extracoes"}
    if desconhecidas:
        raise SystemExit(f"não entendi: {sorted(desconhecidas)}. Use gold, extracoes, bia, oiec_pt, unified ou um caminho")

    if caminhos:
        arquivos = [f for p in caminhos for f in (sorted(p.glob("*.jsonl")) if p.is_dir() else [p])]
        c = inferir_corpus(caminhos[0])
        trabalhos = [(c, inferir_grupo(caminhos[0], c), arquivos)]
    else:
        corpora = [c for c in CORPORA if c in palavras] or list(CORPORA)
        tipos = [t for t in ("gold", "extracoes") if t in palavras] or ["gold", "extracoes"]
        trabalhos = tarefas(corpora, tipos)
    if not trabalhos:
        raise SystemExit(f"nada encontrado em {DADOS}")
    for c, g, arqs in trabalhos:
        processar(arqs, c, g, a.saida)
    print(f"\nfeito. Resultados em {a.saida}")
if __name__ == "__main__":
    main()