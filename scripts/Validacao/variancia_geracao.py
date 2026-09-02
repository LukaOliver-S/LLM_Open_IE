from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from statistics import mean, pstdev

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ/"scripts"/"Validacao"))
from resultados import CORPORA
from carb_score import Tripla, score_sentenca, agregar, binary_linient_tuple_match
from bootstrap_carb import carregar_jsonl, triplas_de, parear, CATEGORIA


def pasta_rodada(respostas_base:Path, lotes:int, k:int) -> Path:
    base = respostas_base / f"{lotes}_batches" 
    return base if k == 1 else base/f"k{k}"

def triplas_por_sentenca(pred_path:Path, gold:list[dict]) -> list[list[Tripla]]:
    mapa = parear(carregar_jsonl(pred_path),gold)
    return [mapa.get(i,[]) for i in range(len(gold))]

def consenso_por_sentenca(rodadas: list[list[Tripla]], limiar: int) -> list[Tripla]:
    """Agrupa triplas equivalentes (lenient match) entre as rodadas; mantém UM
    representante por grupo se o grupo cobrir >= limiar rodadas DISTINTAS."""
    candidatas = [(k_idx, t) for k_idx, rodada in enumerate(rodadas) for t in rodada]
    usadas = [False] * len(candidatas)
    consenso = []
    for i, (k_i, cand) in enumerate(candidatas):
        if usadas[i]:
            continue
        grupo = [i]
        usadas[i] = True
        for j in range(i + 1, len(candidatas)):
            if usadas[j]:
                continue
            k_j, outra = candidatas[j]
            if (binary_linient_tuple_match(cand, outra)[0] > 0.5
                    or binary_linient_tuple_match(outra, cand)[0] > 0.5):
                grupo.append(j)
                usadas[j] = True
        rodadas_no_grupo = {candidatas[idx][0] for idx in grupo}
        if len(rodadas_no_grupo) >= limiar:
            consenso.append(cand)
    return consenso


def main()-> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus",default = 'bia',choices = list(CORPORA))
    ap.add_argument("--tarefa",default = "oiec",choices = list(CATEGORIA))
    ap.add_argument("--modelo",required=True)
    ap.add_argument("--lotes",type = int)
    ap.add_argument('--k',type = int, default = 5, help = "Número de rodadas a considerar (k1...kn)")
    args = ap.parse_args()
    
    cfg = CORPORA[args.corpus]
    gold = [json.loads(l) for l in Path(RAIZ / cfg["gold"]).read_text(encoding="utf-8").splitlines() if l.strip()]
    respostas_base = RAIZ / cfg["respostas"]
    categoria = CATEGORIA[args.tarefa]
    
    rodadas_por_sentenca = []
    f1_por_rodada = []
    for k in range(1,args.k+1):
        pasta = pasta_rodada(respostas_base, args.lotes,k) / categoria
        arquivo = pasta / f"{args.modelo}.jsonl"
        if not arquivo.exists():
             print(f"AVISO: rodada k{k} não encontrada em {arquivo}, pulando.")
             continue
        preds = triplas_por_sentenca(arquivo,gold)
        rodadas_por_sentenca.append(preds)
        acc = [score_sentenca(triplas_de(g.get("gold",[])), preds[i] ) for i,g in enumerate(gold)]
        f1 = agregar(acc)["f1"]
        f1_por_rodada.append(f1)
        print(f"k{k}:F1 = {f1:4f}")
        
    if not f1_por_rodada:
        raise SystemExit("Nenhuma rodada encontrada.")
    
    media = mean(f1_por_rodada)
    desvio = pstdev(f1_por_rodada) if len(f1_por_rodada) > 1 else 0.0
    print(f"\nmédia F1 = {media:.4f}  desvio-padrão = {desvio:.4f}  (n={len(f1_por_rodada)} rodadas)")
    
    limiar = math.ceil(len(rodadas_por_sentenca)/2)
    acc_consenso = []
    for i,g in enumerate(gold):
        rodadas_desta_sentenca = [r[i] for r in rodadas_por_sentenca]
        pred_consenso = consenso_por_sentenca(rodadas_desta_sentenca,limiar)
        acc_consenso.append(score_sentenca(triplas_de(g.get("gold",[])),pred_consenso))
    f1_consenso = agregar(acc_consenso)["f1"]
    print(f"F1 de consenso (voto >= {limiar}/{len(rodadas_por_sentenca)}) = {f1_consenso:.4f}")

    saida = RAIZ / cfg["saida"] / "carb"
    saida.mkdir(parents=True, exist_ok=True)
    csv_path = saida / f"variancia_{args.tarefa}_{args.modelo}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rodada", "f1"])
        for i, f1 in enumerate(f1_por_rodada, 1):
            w.writerow([f"k{i}", f"{f1:.4f}"])
        w.writerow(["media", f"{media:.4f}"])
        w.writerow(["desvio_padrao", f"{desvio:.4f}"])
        w.writerow(["consenso", f"{f1_consenso:.4f}"])
    print(f"\nCSV -> {csv_path}")
    
if __name__ == "__main__":
    main()
    
    
    