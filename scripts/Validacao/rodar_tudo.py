#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rodar_tudo.py
==============

Roda, em sequência, todas as métricas e todos os gráficos dos corpora. A raiz do repositório é descoberta
pela localização deste arquivo, então funciona de qualquer pasta (sempre no repositório onde ele está).

Etapas, para cada corpus:
  0. verificar_respostas      confere duplicadas/faltando (só relatório, não interrompe)
  1. resultados               métricas lexical e exata (gera os CSVs que os gráficos usam)
  2. resultados_por_campo
  3. comparação_batches
  4. contagem_triplas
  5. graficos_resumo
  6. checagem_consenso
  7. gerar_graficos           um gráfico por CSV resultados_Respostas_*.csv existente
  8. bootstrap_ic             IC 95% e diferenças pareadas
  9. grafico_prompts_ic       barras com IC e efeito contra SemRegras
Opcional (--carb): rodar_carb e bootstrap_carb para cada tarefa (lento).

Uma etapa que falha não interrompe as outras; no fim há um resumo com o que falhou.

USO
    python scripts/Validacao/rodar_tudo.py                          # bia e oiec_pt, 10 lotes
    python scripts/Validacao/rodar_tudo.py --corpus bia
    python scripts/Validacao/rodar_tudo.py --corpus oiec_pt oiec_pt_abs --B 10000
    python scripts/Validacao/rodar_tudo.py --carb
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
VAL = RAIZ / "scripts" / "Validacao"
TAREFAS_CARB = ["abstractive", "dpto", "oiec", "ptoiedp", "semregras", "regrasbia", "regrasbiacompleto"]

falhas: list[str] = []


def rodar(rotulo: str, args: list[str]) -> bool:
    print(f"\n>>> {rotulo}", flush=True)
    t0 = time.time()
    r = subprocess.run([sys.executable, "-X", "utf8", *args], cwd=RAIZ)
    ok = r.returncode == 0
    print(f"<<< {'ok' if ok else 'FALHOU (código ' + str(r.returncode) + ')'} em {time.time() - t0:.0f}s", flush=True)
    if not ok:
        falhas.append(rotulo)
    return ok


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", nargs="*", default=["bia", "oiec_pt"])
    ap.add_argument("--lotes", type=int, default=10)
    ap.add_argument("--B", type=int, default=5000, help="reamostragens do bootstrap_ic")
    ap.add_argument("--carb", action="store_true", help="inclui rodar_carb e bootstrap_carb (lento)")
    a = ap.parse_args()

    print(f"raiz: {RAIZ}\npython: {sys.executable}")
    if not (RAIZ / "Respostas").is_dir():
        sys.exit(f"ERRO: {RAIZ / 'Respostas'} não existe; este não parece o repositório oficial.")

    for c in a.corpus:
        print(f"\n{'#' * 20} CORPUS: {c} {'#' * 20}")
        L = str(a.lotes)
        rodar(f"{c}: verificar_respostas", [str(VAL / "verificar_respostas.py"), "--corpus", c, "--lotes", L])
        rodar(f"{c}: resultados", [str(VAL / "resultados.py"), "--corpus", c])
        rodar(f"{c}: resultados_por_campo", [str(VAL / "resultados_por_campo.py"), "--corpus", c, "--lotes", L])
        rodar(f"{c}: comparação_batches", [str(VAL / "comparação_batches.py"), "--corpus", c, "--lotes", L])
        rodar(f"{c}: contagem_triplas", [str(VAL / "contagem_triplas.py"), "--corpus", c, "--lotes", L])
        rodar(f"{c}: graficos_resumo", [str(VAL / "graficos_resumo.py"), "--corpus", c, "--lotes", L])
        rodar(f"{c}: checagem_consenso", [str(VAL / "checagem_consenso.py"), "--corpus", c, "--lotes", L])

        csvs = sorted((RAIZ / "Outputs" / "metricas" / c / f"{L}_batches").glob("resultados_Respostas_*.csv"))
        if csvs:
            rodar(f"{c}: gerar_graficos ({len(csvs)} CSVs)",
                  [str(VAL / "gerar_graficos.py"), *[str(p.relative_to(RAIZ)) for p in csvs]])
        else:
            print(f"[{c}] nenhum resultados_Respostas_*.csv, pulando gerar_graficos")
            falhas.append(f"{c}: gerar_graficos (sem CSVs)")

        rodar(f"{c}: bootstrap_ic", [str(VAL / "bootstrap_ic.py"), "--corpus", c, "--lotes", L, "--B", str(a.B)])
        rodar(f"{c}: grafico_prompts_ic", [str(VAL / "grafico_prompts_ic.py"), "--corpus", c])

        if a.carb:
            for t in TAREFAS_CARB:
                rodar(f"{c}/{t}: rodar_carb", [str(VAL / "rodar_carb.py"), "--corpus", c, "--tarefa", t])
                rodar(f"{c}/{t}: bootstrap_carb", [str(VAL / "bootstrap_carb.py"), "--corpus", c, "--tarefa", t])

    print("\n" + "=" * 60)
    if falhas:
        print(f"{len(falhas)} etapa(s) com problema:")
        for f in falhas:
            print("  -", f)
    else:
        print("FEITO: todas as etapas terminaram sem erro.")


if __name__ == "__main__":
    main()
