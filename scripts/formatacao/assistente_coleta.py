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

TAREFAS = {
    "abstractive": {
        "prompt": RAIZ / "prompts" / "promptAbstractiveOpenIE.txt",
        "categoria": "Respostas AbstractiveOpenIE",
        "placeholder": "[INPUT]",
    },
    "dpto": {
        "prompt": RAIZ / "prompts" / "promptDPTO-IE_extrativo.txt",
        "categoria": "Respostas ExtrativoDPTO-IE",
        "placeholder": None,
    },
    "oiec": {
        "prompt": RAIZ / "prompts" / "promptOIEC-PT_extrativo.txt",
        "categoria": "Respostas ExtrativoOIEC-PT",
        "placeholder": None,
    },
    "ptoiedp": {
        "prompt": RAIZ / "prompts" / "promptPTOIE-dp_extrativo.txt",
        "categoria": "Respostas ExtrativoPTOIE-DP",
        "placeholder": None,
    },
}

def carregar_sentencas(caminho: Path) -> list[dict]:
    texto = caminho.read_text(encoding="utf-8").strip()
    if texto.startswith("["):
        return json.loads(texto)
    return [json.loads(linha) for linha in texto.splitlines() if linha.strip()]


FORMATO_REFORCO = """

IMPORTANTE -- formato de saída obrigatório: JSONL (um objeto JSON por linha, SEM colchetes
envolvendo tudo e SEM vírgula entre os objetos). Cada linha corresponde a uma sentença, na
mesma ordem em que foram apresentadas acima. Exemplo (frases fictícias, apenas para ilustrar o
formato -- não fazem parte do texto a ser processado):

{"sentence":"Maria Silva, nascida em 1990, trabalha como engenheira, e seu marido, Carlos Silva, que se formou em 2010, trabalha como médico.","relations":[{"arg1":"Maria Silva","rel":"nascida em","arg2":"1990"},{"arg1":"Maria Silva","rel":"trabalha como","arg2":"engenheira"},{"arg1":"Carlos Silva","rel":"se formou em","arg2":"2010"},{"arg1":"Carlos Silva","rel":"trabalha como","arg2":"médico"},{"arg1":"seu marido","rel":"é","arg2":"Carlos Silva"}]}
{"sentence":"A empresa Alfa Tech lançou um novo produto em março de 2022.","relations":[{"arg1":"A empresa Alfa Tech","rel":"lançou","arg2":"um novo produto"},{"arg1":"A empresa Alfa Tech","rel":"lançou em","arg2":"março de 2022"}]}

Não devolva as triplas soltas fora de "relations"; não repita a sentença como um item separado; se
nenhuma relação for encontrada em uma sentença, use "relations": [].

E Cada trecho do texto acima está marcado com [S1], [S2], etc. -- cada marcador indica o INÍCIO de
uma sentença nova e independente. NUNCA funda duas sentenças de marcadores diferentes em um único
item de saída, mesmo que pareçam continuar uma a outra. Gere exatamente um item de saída por
marcador [Sn], com o texto daquele trecho (sem incluir "[Sn]") no campo "sentence".
"""


def montar_texto(tarefa: dict, sentencas: list[dict]) -> str:
    prompt = tarefa["prompt"].read_text(encoding="utf-8")
    if tarefa["placeholder"]:
        texto_bloco = "\n".join(
            f"[S{i+1}] {s.get('sentence', '')}" for i, s in enumerate(sentencas)
        )
        texto = prompt.replace(tarefa["placeholder"], texto_bloco)
    else:
        bloco = json.dumps(sentencas, ensure_ascii=False, indent=2)
        texto = f"{prompt}\n\nProcesse as seguintes sentenças:\n{bloco}"
    return texto + FORMATO_REFORCO

def ler_colagem() -> str:
    print("\nCole a resposta da LLM abaixo. Quando terminar, digite sozinho numa linha: FIM\n")
    linhas = []
    while True:
        linha = input()
        if linha.strip() == "FIM":
            break
        linhas.append(linha)
    return "\n".join(linhas)


def reconstruir_arquivo_final(pasta_bruto: Path, arquivos_lote: list[Path], caminho_final: Path) -> None:
    """Concatena todos os lotes já coletados, na ordem certa, no arquivo final."""
    partes_texto = []
    for arquivo_lote in arquivos_lote:
        n_lote = int(arquivo_lote.stem.rsplit("_", 1)[1])
        caminho_bruto = pasta_bruto / f"parte_{n_lote}.txt"
        if caminho_bruto.exists():
            partes_texto.append(caminho_bruto.read_text(encoding="utf-8"))
    caminho_final.write_text("\n".join(partes_texto), encoding="utf-8")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tarefa", choices=TAREFAS.keys(), required=True)
    parser.add_argument("--modelo", required=True, help="Nome do modelo (vira o nome do arquivo de saída)")
    parser.add_argument("--lotes", type=int, default=10, help="Tamanho do lote (pasta sentencas/<N>_sentencas)")
    parser.add_argument("--apenas-lotes", default=None,
                         help="Lista de números de lote a (re)coletar, separados por vírgula "
                              "(ex.: 1,2,3,5,7,9,21). Se omitido, roda todos os que ainda faltam.")
    parser.add_argument("--sentencas-base", default="sentencas",
                         help="Pasta base dos lotes (ex.: 'sentencas_oiecpt' para o corpus OIEC-PT-GOLD).")
    parser.add_argument("--respostas-base", default="Respostas",
                         help="Pasta base onde salvar as respostas (deve casar com --sentencas-base "
                              "para não misturar corpora diferentes).")
    args = parser.parse_args()

    tarefa = TAREFAS[args.tarefa]
    pasta_lotes = RAIZ / args.sentencas_base / f"{args.lotes}_sentencas"
    arquivos_lote = sorted(
        pasta_lotes.glob("sentencas_parte_*.jsonl"),
        key=lambda p: int(p.stem.rsplit("_", 1)[1]),
    )
    if not arquivos_lote:
        raise FileNotFoundError(f"Nenhum lote encontrado em {pasta_lotes}")

    # a pasta bruta é isolada por TAREFA também -- sem isso, lotes já
    # coletados para uma tarefa seriam confundidos com os de outra tarefa
    # que usa o mesmo modelo e o mesmo tamanho de lote
    pasta_bruto = RAIZ / args.respostas_base / f"{args.lotes}_batches" / "_bruto" / args.tarefa / args.modelo
    pasta_bruto.mkdir(parents=True, exist_ok=True)

    pasta_final = RAIZ / args.respostas_base / f"{args.lotes}_batches" / tarefa["categoria"]
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