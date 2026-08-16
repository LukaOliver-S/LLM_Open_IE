# scripts/Validacao/rodar_carb.py
"""
Pontua TODOS os modelos de um corpus/tarefa com CaRB (carb_score.py),
salva CSV e plota F1-CaRB por modelo (com IC 95% bootstrap opcional).

Uso:
    python -X utf8 scripts/Validacao/rodar_carb.py --corpus oiec_pt --tarefa dpto --ic
    python -X utf8 scripts/Validacao/rodar_carb.py --corpus bia --tarefa dpto
"""
from __future__ import annotations
import argparse, csv, json, sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")                       # salva PNG sem abrir janela
import matplotlib.pyplot as plt

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "scripts" / "Validacao"))
from resultados import CORPORA
from carb_score import agregar
from bootstrap_carb import acumuladores_modelo, CATEGORIA   # reusa loading/pairing

# modelos especializados (verde); resto = LLM (azul). ajuste se preciso.
ESPEC = {"ptoie-flair", "dptoie-py", "dptoie", "respostadptoie-py"}
COR_ESPEC, COR_LLM = "#009E73", "#0072B2"    # Okabe-Ito (consistente c/ os outros gráficos)

def eh_espec(nome: str) -> bool:
    return nome.lower().replace("respostas_", "").replace("respostas", "") in ESPEC

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="bia", choices=list(CORPORA))
    ap.add_argument("--tarefa", default="dpto", choices=list(CATEGORIA))
    ap.add_argument("--ic", action="store_true", help="calcula IC 95% bootstrap (barras de erro)")
    ap.add_argument("--B", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    cfg = CORPORA[args.corpus]
    gold = [json.loads(l) for l in
            Path(RAIZ / cfg["gold"]).read_text(encoding="utf-8").splitlines() if l.strip()]
    pasta = RAIZ / cfg["respostas"] / "10_batches" / CATEGORIA[args.tarefa]
    arquivos = sorted(pasta.glob("*.jsonl"))
    if not arquivos:
        raise FileNotFoundError(f"Nenhuma resposta em {pasta}")

    n = len(gold)
    amostras = None
    if args.ic:
        rng = np.random.default_rng(args.seed)
        amostras = [rng.integers(0, n, size=n) for _ in range(args.B)]

    linhas = []   # (modelo, tipo, P, R, F1, lo, hi)
    for mp in arquivos:
        acc = acumuladores_modelo(mp, gold)
        m = agregar(acc)
        lo = hi = None
        if amostras is not None:
            boot = np.array([agregar([acc[i] for i in idx])["f1"] for idx in amostras])
            lo, hi = np.percentile(boot, [2.5, 97.5])
        linhas.append((mp.stem, "Especializado" if eh_espec(mp.stem) else "LLM",
                       m["precision"], m["recall"], m["f1"], lo, hi))

    linhas.sort(key=lambda x: x[4], reverse=True)   # por F1

    # ---- CSV ----
    saida = RAIZ / cfg["saida"] / "carb"
    saida.mkdir(parents=True, exist_ok=True)
    csv_path = saida / f"carb_{args.corpus}_{args.tarefa}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["modelo", "tipo", "precision", "recall", "f1", "ic_lo", "ic_hi"])
        for r in linhas:
            w.writerow([r[0], r[1]] + [f"{v:.4f}" if v is not None else "" for v in r[2:]])
    print("CSV  ->", csv_path)

    # ---- gráfico: F1 por modelo (barh), especializados destacados ----
    nomes = [r[0] for r in linhas]
    f1s   = [r[4] for r in linhas]
    cores = [COR_ESPEC if r[1] == "Especializado" else COR_LLM for r in linhas]
    y = np.arange(len(nomes))[::-1]     # maior no topo

    fig, ax = plt.subplots(figsize=(8, 0.55 * len(nomes) + 1.5))
    barras = ax.barh(y, f1s, color=cores, edgecolor="black", linewidth=0.4)

    if amostras is not None:
        err = np.array([[r[4] - r[5] for r in linhas], [r[6] - r[4] for r in linhas]])
        ax.errorbar(f1s, y, xerr=err, fmt="none", ecolor="black",
                    elinewidth=1, capsize=3)

    for yi, v in zip(y, f1s):
        ax.text(v + 0.01, yi, f"{v:.3f}", va="center", fontsize=9)

    ax.set_yticks(y); ax.set_yticklabels(nomes)
    ax.set_xlabel("F1 — CaRB"); ax.set_xlim(0, max(f1s) * 1.18)
    ax.set_title(f"CaRB — {args.corpus} / {args.tarefa}"
                 + ("  (IC 95% bootstrap)" if amostras is not None else ""))
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=COR_ESPEC, label="Especializado"),
                       Patch(color=COR_LLM, label="LLM")], loc="lower right")
    ax.grid(axis="x", linestyle=":", alpha=0.5)
    fig.tight_layout()
    png = saida / f"carb_{args.corpus}_{args.tarefa}.png"
    fig.savefig(png, dpi=150); print("PNG  ->", png)

if __name__ == "__main__":
    main()