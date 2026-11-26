#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
correlacao_triplas_f1.py
=========================

Pergunta: quando um prompt faz o LLM gerar MAIS triplas do que o gold tem, o F1 cai?

Cada combinação (LLM, prompt) é um ponto com dois números:
    razão = triplas geradas pelo modelo / triplas do gold          (coluna razao_pred_gold do contagem_triplas)
    F1    = F1 lexical dessa combinação                            (coluna f1_lexical do resultados)
O script calcula a correlação entre as duas colunas e desenha o gráfico de dispersão.
Faz o mesmo para precisão e recall, que mostram ONDE o F1 muda.

COMO O CÁLCULO FUNCIONA (resumo; os comentários do código detalham)
  1. Pearson r: mede relação LINEAR. r = soma((x-média_x)*(y-média_y)) / (n * desvio_x * desvio_y). Vai de -1 a +1.
  2. Spearman rho: é o Pearson aplicado aos POSTOS (1º, 2º, 3º...) em vez dos valores. Mede se a ordem acompanha,
     mesmo que a relação não seja uma reta, e sofre menos com pontos extremos.
  3. IC 95% por bootstrap: sorteia B vezes n pontos COM reposição, recalcula o r em cada sorteio e usa os percentis
     2,5 e 97,5. Se o intervalo não contém 0, a correlação é distinguível de nenhuma relação.
  4. "Dentro de cada LLM": subtrai de x e de y a média do próprio LLM antes de correlacionar. Assim some a diferença
     entre modelos (um modelo bom em tudo) e sobra só o efeito de TROCAR O PROMPT para o mesmo LLM.

LIMITES
  - São poucos pontos (uns 20), então o IC é largo. Correlação não prova causa.
  - Só entram combinações LLM x prompt. Os extratores locais (pasta SistemasExtrativos) ficam de fora, pois não têm prompt.
  - Respostas que cobrem menos de 95% das sentenças do gold ficam de fora (--cobertura-minima), pois o recall delas está subestimado.

USO (da raiz do repositório)
    python scripts/Validacao/correlacao_triplas_f1.py --corpus bia oiec_pt
Saída: Outputs/analise_regras/<corpus>/correlacao_triplas_f1_pontos.csv, ..._resumo.csv e o gráfico .png/.pdf
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]

plt.rcParams.update({"axes.grid": False, "axes.spines.top": False, "axes.spines.right": False,
                     "savefig.dpi": 300, "savefig.bbox": "tight"})

PASTA_EXCLUIDA = "SistemasExtrativos"          # extratores locais não têm prompt
ROTULO_PROMPT = {"SemRegras": "Sem regras", "ExtrativoDPTO-IE": "DPTO-IE", "ExtrativoOIEC-PT": "OIEC-PT",
                 "ExtrativoOIEC-PT-simples": "OIEC-PT (simples)",
                 "ExtrativoPTOIE-DP": "PTOIE-DP", "ExtrativoBIA-completo": "BIA", "ExtrativoBIA": "BIA (simples)"}
COR_PROMPT = {"SemRegras": "#9e9e9e", "ExtrativoDPTO-IE": "#4c78a8", "ExtrativoOIEC-PT": "#f58518",
              "ExtrativoOIEC-PT-simples": "#f9c784",
              "ExtrativoPTOIE-DP": "#54a24b", "ExtrativoBIA-completo": "#b279a2", "ExtrativoBIA": "#e7a8d0"}
MARCADORES = ["o", "s", "^", "D", "v", "P", "X"]


def canon(modelo: str) -> str:
    """'respostaGrok4.0Fast' e 'Grok4.0Fast' são o mesmo LLM: tira o prefixo 'resposta(s)_'."""
    return re.sub(r"^respostas?_?", "", modelo)


def carregar_pontos(corpus: str, lotes: int, cob_min: float = 0.95, ignorar=("ExtrativoBIA",)) -> pd.DataFrame:
    """Junta, por (prompt, modelo), o F1/precisão/recall do resultados.py com a razão do contagem_triplas.py.
    Descarta respostas que cobrem menos de cob_min das sentenças do gold: recall subestimado por coleta incompleta."""
    pasta = RAIZ / "Outputs" / "metricas" / corpus / f"{lotes}_batches"
    res, cont = [], []
    for f in sorted(pasta.glob("resultados_Respostas_*.csv")):
        prompt = f.stem[len("resultados_Respostas_"):]            # 'ExtrativoDPTO-IE', 'SemRegras', ...
        if prompt == PASTA_EXCLUIDA or prompt in ignorar:
            continue
        d = pd.read_csv(f)
        d["prompt"] = prompt
        res.append(d[["prompt", "modelo", "precisao_lexical", "recall_lexical", "f1_lexical", "n_frases_gold", "n_gold_sem_cobertura"]])
    for f in sorted(pasta.glob("contagem_triplas_Respostas_*.csv")):
        prompt = f.stem[len("contagem_triplas_Respostas_"):]
        if prompt == PASTA_EXCLUIDA or prompt in ignorar:
            continue
        d = pd.read_csv(f)
        d["prompt"] = prompt
        cont.append(d[["prompt", "modelo", "media_triplas_pred_por_frase", "razao_pred_gold"]])
    if not res or not cont:
        raise SystemExit(f"[{corpus}] faltam CSVs em {pasta}: rode resultados.py e contagem_triplas.py antes.")
    pontos = pd.concat(res).merge(pd.concat(cont), on=["prompt", "modelo"], how="inner", validate="one_to_one")
    pontos["cobertura"] = 1 - pontos["n_gold_sem_cobertura"] / pontos["n_frases_gold"]
    fora = pontos[pontos["cobertura"] < cob_min]
    for _, r in fora.iterrows():
        print(f"  [{corpus}] fora da correlação por cobertura {r['cobertura']:.1%}: {r['prompt']} / {r['modelo']}")
    pontos = pontos[pontos["cobertura"] >= cob_min].drop(columns=["n_frases_gold", "n_gold_sem_cobertura"]).reset_index(drop=True)
    pontos["llm"] = pontos["modelo"].map(canon)
    pontos.insert(0, "corpus", corpus)
    return pontos


def pearson(x: np.ndarray, y: np.ndarray) -> float:
    """r de Pearson. Devolve NaN se x ou y for constante (desvio zero), onde o r não existe."""
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def postos(v: np.ndarray) -> np.ndarray:
    """Posto de cada valor (1 = menor). Empates recebem a média dos postos, como no Spearman padrão."""
    return pd.Series(v).rank(method="average").to_numpy()


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    """rho de Spearman = Pearson dos postos."""
    return pearson(postos(x), postos(y))


def ic_bootstrap(x: np.ndarray, y: np.ndarray, B: int, rng: np.random.Generator):
    """IC 95% do r de Pearson: B vezes sorteia n índices COM reposição, recalcula o r e pega os percentis 2,5 e 97,5."""
    n = len(x)
    rs = []
    for _ in range(B):
        i = rng.integers(0, n, size=n)
        r = pearson(x[i], y[i])
        if not np.isnan(r):                         # sorteio degenerado (x ou y constante) não conta
            rs.append(r)
    if len(rs) < B * 0.5:
        return float("nan"), float("nan")
    return tuple(np.percentile(rs, [2.5, 97.5]))


def tirar_media_do_llm(df: pd.DataFrame, col: str) -> np.ndarray:
    """Subtrai de cada valor a média do próprio LLM: remove a diferença entre modelos e deixa o efeito do prompt."""
    return (df[col] - df.groupby("llm")[col].transform("mean")).to_numpy()


def resumo_correlacoes(p: pd.DataFrame, B: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    linhas = []
    # (nome, coluna do y). x é sempre a razão preditas/gold.
    for nome, col in [("F1", "f1_lexical"), ("Precisão", "precisao_lexical"), ("Recall", "recall_lexical")]:
        x, y = p["razao_pred_gold"].to_numpy(), p[col].to_numpy()
        lo, hi = ic_bootstrap(x, y, B, rng)
        linhas.append({"corpus": p["corpus"].iloc[0], "analise": "todos os pontos", "metrica": nome, "n_pontos": len(p),
                       "pearson": round(pearson(x, y), 3), "ic95_inf": round(lo, 3), "ic95_sup": round(hi, 3),
                       "spearman": round(spearman(x, y), 3)})
        # dentro de cada LLM: só entram LLMs com pelo menos 2 prompts (senão a média anula o ponto)
        q = p[p.groupby("llm")["llm"].transform("count") >= 2].reset_index(drop=True)
        xd, yd = tirar_media_do_llm(q, "razao_pred_gold"), tirar_media_do_llm(q, col)
        lo, hi = ic_bootstrap(xd, yd, B, rng)
        linhas.append({"corpus": p["corpus"].iloc[0], "analise": "dentro de cada LLM", "metrica": nome, "n_pontos": len(q),
                       "pearson": round(pearson(xd, yd), 3), "ic95_inf": round(lo, 3), "ic95_sup": round(hi, 3),
                       "spearman": round(spearman(xd, yd), 3)})
    return pd.DataFrame(linhas)


def grafico(p: pd.DataFrame, resumo: pd.DataFrame, corpus: str, saida: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5.5))
    llms = sorted(p["llm"].unique())
    marca = {m: MARCADORES[i % len(MARCADORES)] for i, m in enumerate(llms)}
    for _, r in p.iterrows():
        ax.scatter(r["razao_pred_gold"], r["f1_lexical"], s=60, marker=marca[r["llm"]],
                   color=COR_PROMPT.get(r["prompt"], "#333333"), edgecolor="#333333", linewidth=0.5, zorder=3)
    # reta de mínimos quadrados (só para guiar o olho)
    x, y = p["razao_pred_gold"].to_numpy(), p["f1_lexical"].to_numpy()
    if len(p) >= 3 and np.std(x) > 0:
        a, b = np.polyfit(x, y, 1)
        xs = np.linspace(x.min(), x.max(), 50)
        ax.plot(xs, a * xs + b, color="#333333", linewidth=1, linestyle="--", zorder=2)
    ax.axvline(1.0, color="#999999", linewidth=0.8, zorder=1)           # razão 1 = mesmo número de triplas do gold
    ax.text(1.0, ax.get_ylim()[1], " mesmo nº de triplas do gold", fontsize=8, va="top", color="#666666")
    r_tudo = resumo[(resumo.analise == "todos os pontos") & (resumo.metrica == "F1")].iloc[0]
    r_llm = resumo[(resumo.analise == "dentro de cada LLM") & (resumo.metrica == "F1")].iloc[0]
    ax.set_title(f"Triplas geradas vs F1, corpus {corpus}\n"
                 f"Pearson r = {r_tudo['pearson']:+.2f} (IC 95% [{r_tudo['ic95_inf']:+.2f}, {r_tudo['ic95_sup']:+.2f}]), "
                 f"dentro de cada LLM r = {r_llm['pearson']:+.2f}", fontsize=10)
    ax.set_xlabel("Triplas geradas / triplas do gold")
    ax.set_ylabel("F1 lexical")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    # duas legendas: cor = prompt, forma = LLM
    h_prompt = [plt.Line2D([], [], marker="o", linestyle="", color=COR_PROMPT[k], markeredgecolor="#333333", label=ROTULO_PROMPT[k])
                for k in COR_PROMPT if k in set(p["prompt"])]
    h_llm = [plt.Line2D([], [], marker=marca[m], linestyle="", color="#bbbbbb", markeredgecolor="#333333", label=m) for m in llms]
    leg1 = ax.legend(handles=h_prompt, title="Prompt (cor)", frameon=False, loc="upper right", fontsize=8)
    ax.add_artist(leg1)
    ax.legend(handles=h_llm, title="LLM (forma)", frameon=False, loc="lower left", fontsize=8)
    for ext in ("png", "pdf"):
        fig.savefig(saida / f"correlacao_triplas_f1.{ext}")
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", nargs="*", default=["bia", "oiec_pt"])
    ap.add_argument("--lotes", type=int, default=10)
    ap.add_argument("--B", type=int, default=5000)
    ap.add_argument("--semente", type=int, default=42)
    ap.add_argument("--cobertura-minima", type=float, default=0.95)
    ap.add_argument("--ignorar", nargs="*", default=["ExtrativoBIA"], help="pastas de prompt a deixar de fora (padrão: BIA simples)")
    a = ap.parse_args()
    pd.set_option("display.width", 200, "display.max_columns", 20)
    for c in a.corpus:
        p = carregar_pontos(c, a.lotes, a.cobertura_minima, a.ignorar)
        resumo = resumo_correlacoes(p, a.B, a.semente)
        saida = RAIZ / "Outputs" / "analise_regras" / c
        saida.mkdir(parents=True, exist_ok=True)
        p.to_csv(saida / "correlacao_triplas_f1_pontos.csv", index=False)
        resumo.to_csv(saida / "correlacao_triplas_f1_resumo.csv", index=False)
        grafico(p, resumo, c, saida)
        print(f"\n=== {c}: {len(p)} combinações LLM x prompt ===")
        print(resumo.drop(columns="corpus").to_string(index=False))
        print("saída:", saida)


if __name__ == "__main__":
    main()
