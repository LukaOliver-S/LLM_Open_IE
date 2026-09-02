"""
assistente_coleta.py
=====================
Ajudante semi-automático para coletar respostas de LLMs via interface de
chat, sem usar API paga. Para cada lote de sentenças: monta o texto do
prompt, copia para a área de transferência, espera você colar a resposta
de volta, e salva no lugar certo -- retomável a qualquer momento.

Uso:
    python assistente_coleta.py --tarefa abstractive --modelo Claude_Sonnet5 --lotes 10
    python assistente_coleta.py --tarefa dpto --modelo Grok4.0Fast --lotes 10
    python assistente_coleta.py --tarefa oiec --modelo Gemini3.1Pro --lotes 10
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    import pyperclip
except ImportError:
    pyperclip = None

RAIZ = Path(__file__).resolve().parents[2]  # LLM_Open_IE/

import sys
sys.path.insert(0, str(RAIZ / "scripts" / "Validacao"))
from resultados import CORPORA, CORPUS_PADRAO, resolver_corpus  # registro de corpora
from _coleta_comum import(
    TAREFAS, carregar_sentencas, montar_texto, pasta_rodada, reconstruir_arquivo_final
)



def ler_colagem() -> str:
    print("\nCole a resposta da LLM abaixo. Quando terminar, digite sozinho numa linha: FIM\n")
    linhas = []
    while True:
        linha = input()
        if linha.strip() == "FIM":
            break
        linhas.append(linha)
    return "\n".join(linhas)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tarefa", choices=TAREFAS.keys(), required=True)
    parser.add_argument("--modelo", required=True, help="Nome do modelo (vira o nome do arquivo de saída)")
    parser.add_argument("--lotes", type=int, default=10, help="Tamanho do lote (pasta sentencas/<N>_sentencas)")
    parser.add_argument("--apenas-lotes", default=None,
                         help="Lista de números de lote a (re)coletar, separados por vírgula "
                              "(ex.: 1,2,3,5,7,9,21). Se omitido, roda todos os que ainda faltam.")
    parser.add_argument("--corpus", default="bia", choices=list(CORPORA),
                         help="Corpus (define sentencas-base e respostas-base). Default: bia")
    parser.add_argument("--sentencas-base", default=None,
                         help="Sobrepõe a pasta base dos lotes do corpus (ex.: 'sentencas_oiecpt').")
    parser.add_argument("--respostas-base", default=None,
                         help="Sobrepõe a pasta base onde salvar as respostas do corpus.")
    
    parser.add_argument("--k", type = int,default = 1, help = "Número da rodada de repetição (1 = coleta original).")
    
    parser.add_argument("--forcar", action = "store_true", help = "Sobrescreve o arquivo final mesmo se já existir com conteúdo diferente")
    
    args = parser.parse_args()

    cfg = CORPORA[args.corpus]
    sentencas_base = args.sentencas_base or cfg["sentencas"]
    respostas_base = args.respostas_base or cfg["respostas"]

    tarefa = TAREFAS[args.tarefa]
    pasta_lotes = RAIZ / sentencas_base / f"{args.lotes}_sentencas"
    arquivos_lote = sorted(
        pasta_lotes.glob("sentencas_parte_*.jsonl"),
        key=lambda p: int(p.stem.rsplit("_", 1)[1]),
    )
    if not arquivos_lote:
        raise FileNotFoundError(f"Nenhum lote encontrado em {pasta_lotes}")

    # a pasta bruta é isolada por TAREFA também -- sem isso, lotes já
    # coletados para uma tarefa seriam confundidos com os de outra tarefa
    # que usa o mesmo modelo e o mesmo tamanho de lote
    raiz_rodada = pasta_rodada(RAIZ / respostas_base, args.lotes, args.k)
    pasta_bruto = raiz_rodada/"_bruto"/args.tarefa/args.modelo
    pasta_bruto.mkdir(parents=True, exist_ok=True)

    pasta_final = raiz_rodada / tarefa["categoria"]
    pasta_final.mkdir(parents=True, exist_ok=True)
    caminho_final = pasta_final / f"{args.modelo}.jsonl"

    if args.apenas_lotes:
        alvo = {int(x.strip()) for x in args.apenas_lotes.split(",")}
        lotes_para_coletar = [a for a in arquivos_lote if int(a.stem.rsplit("_", 1)[1]) in alvo]
        if not lotes_para_coletar:
            raise ValueError(f"Nenhum lote encontrado para os números: {sorted(alvo)}")
        for arquivo_lote in lotes_para_coletar:
            n_lote = int(arquivo_lote.stem.rsplit("_", 1)[1])
            caminho_bruto = pasta_bruto / f"parte_{n_lote}.txt"
            if caminho_bruto.exists():
                caminho_bruto.unlink()
                print(f"Lote {n_lote}: rascunho anterior removido, será recoletado.")
    else:
        lotes_para_coletar = arquivos_lote

    for arquivo_lote in lotes_para_coletar:
        n_lote = int(arquivo_lote.stem.rsplit("_", 1)[1])
        caminho_bruto = pasta_bruto / f"parte_{n_lote}.txt"

        if caminho_bruto.exists():
            print(f"Lote {n_lote}/{len(arquivos_lote)} já coletado, pulando.")
            continue

        sentencas = carregar_sentencas(arquivo_lote)
        texto = montar_texto(tarefa, sentencas)

        if pyperclip:
            pyperclip.copy(texto)
            print(f"\n=== Lote {n_lote}/{len(arquivos_lote)} copiado para a área de transferência ===")
        else:
            print(f"\n=== Lote {n_lote}/{len(arquivos_lote)} (pyperclip não instalado -- copie manualmente abaixo) ===")
            print(texto)

        print("Cole no chat da LLM, espere a resposta completa, copie-a inteira.")
        resposta = ler_colagem()
        caminho_bruto.write_text(resposta, encoding="utf-8")
        print(f"Salvo: {caminho_bruto}")

        reconstruir_arquivo_final(pasta_bruto, arquivos_lote, caminho_final)

    # garante que o arquivo final existe/está atualizado mesmo se todos os
    # lotes já estavam prontos (o loop acima pode não ter reconstruído nada)
    reconstruir_arquivo_final(pasta_bruto, arquivos_lote, caminho_final)

    print(f"\nConcluído. Arquivo final: {caminho_final}")


if __name__ == "__main__":
    main()