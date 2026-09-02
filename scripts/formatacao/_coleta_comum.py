

from __future__ import annotations
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

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

def carregar_sentencas(caminho:Path)-> list[dict]:
    texto = caminho.read_text(encoding = 'utf-8').strip()
    if texto.startswith("["):
        return json.loads(texto)
    return [json.loads(linha) for linha in texto.splitlines() if linha.strip()]


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

def pasta_rodada(respostas_base:Path, lotes: int, k:int) -> Path:
    base = respostas_base / f"{lotes}_batches"
    return base if k == 1 else base /f"k{k}"

def escrever_protegido(caminho: Path, conteudo: str,
                       forcar:bool = False) -> None:
    if caminho.exists() and not forcar:
        existente = caminho.read_text(encoding = 'utf-8')
        if existente!=conteudo:
            raise FileExistsError(
                  f"{caminho} já existe com conteúdo diferente. "
                f"Use --forcar para sobrescrever intencionalmente."
            )
    return caminho.write_text(conteudo,encoding= "utf-8")



def reconstruir_arquivo_final(pasta_bruto: Path, arquivos_lote: list[Path], caminho_final: Path) -> None:
    """Concatena todos os lotes já coletados, na ordem certa, no arquivo final."""
    partes_texto = []
    for arquivo_lote in arquivos_lote:
        n_lote = int(arquivo_lote.stem.rsplit("_", 1)[1])
        caminho_bruto = pasta_bruto / f"parte_{n_lote}.txt"
        if caminho_bruto.exists():
            partes_texto.append(caminho_bruto.read_text(encoding="utf-8"))
    caminho_final.write_text("\n".join(partes_texto), encoding="utf-8")
