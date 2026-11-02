#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gerar_planilha_comparativa.py
===============================

Gera UMA planilha Excel (.xlsx) para inspeção qualitativa: uma aba por
tarefa (pasta), uma linha por frase, e uma coluna para o Gabarito (Gold) +
uma coluna para cada modelo, mostrando as triplas extraídas com marcação
visual de acerto/erro:

    ✓✓ tripla = casamento EXATO com uma tripla do gold
    ✓  tripla = casamento LEXICAL (overlap > 50%) com uma tripla do gold
    ✗  tripla = falso positivo (não bateu com nada do gold)
    🟡 tripla = falso positivo em que TODOS os modelos da aba concordam
    🔷 tripla = falso positivo em que só as LLMs comerciais concordam entre si

No gabarito:
    ⚠  triplas que NENHUM modelo conseguiu recuperar (nem lexical) ficam
       marcadas em vermelho/negrito — útil pra achar os casos mais difíceis.
    ⭐ triplas que TODOS os modelos da aba recuperaram (cada um por conta
       própria) ficam marcadas em roxo/negrito — fatos "fáceis"/inequívocos,
       úteis como contraste dos casos difíceis acima.

Não depende do resultados.py nem do corrigir_gemini.py: é 100% autônomo
(faz sua própria leitura robusta de JSON e agrupamento por frase).

USO
----
    # Modo automático: procura pastas "Respostas *" na pasta atual
    python3 gerar_planilha_comparativa.py --gold bia_gold_sentences.jsonl

    # Escolher pastas manualmente
    python3 gerar_planilha_comparativa.py --gold bia_gold_sentences.jsonl \
        --pastas "Respostas AbstractiveOpenIE" "Respostas ExtrativoDPTO-IE"

    # Escolher nome de saída e limiar de overlap lexical
    python3 gerar_planilha_comparativa.py --gold bia_gold_sentences.jsonl \
        --saida comparativo.xlsx --limiar 0.5

Requer: openpyxl (pip install openpyxl --break-system-packages)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from openpyxl import Workbook
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# --------------------------------------------------------------------------- #
# 1. LEITURA ROBUSTA DE JSON "SUJO" (mesma técnica usada nos outros scripts)
# --------------------------------------------------------------------------- #

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts" / "Validacao"))

from resultados import CORPORA, resolver_corpus




_RE_MARKDOWN_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$", re.MULTILINE)
_RE_ESPACOS = re.compile(r"\s+")


def ler_todos_os_objetos_json(caminho: Path) -> List[Any]:
    texto = caminho.read_text(encoding="utf-8", errors="replace").strip()
    texto = _RE_MARKDOWN_FENCE.sub("", texto).strip()
    objetos: List[Any] = []
    decoder = json.JSONDecoder()
    idx, n = 0, len(texto)
    while idx < n:
        while idx < n and texto[idx] in " \n\r\t,":
            idx += 1
        if idx >= n:
            break
        try:
            obj, fim = decoder.raw_decode(texto, idx)
            objetos.append(obj)
            idx = fim
        except json.JSONDecodeError:
            idx += 1
    return objetos


def achatar(objetos: List[Any]) -> List[Any]:
    achatado = []
    for obj in objetos:
        achatado.extend(obj) if isinstance(obj, list) else achatado.append(obj)
    return achatado


def normalizar_frase(s: str) -> str:
    s = (s or "").strip().lower()
    return _RE_ESPACOS.sub(" ", s).strip(" .:;,-")


def agrupar_por_frase(itens: List[Any]) -> List[dict]:
    """Agrupa itens em {"sentence":..., "relations":[{arg1,rel,arg2}, ...]},
    lidando tanto com formato já agrupado quanto achatado (tripla solta
    com 'sentence' embutida), na ordem de primeira aparição."""
    ordem: List[str] = []
    frase_original: Dict[str, str] = {}
    triplas: Dict[str, List[Dict[str, str]]] = {}
    vistos: Dict[str, set] = {}

    for item in itens:
        if not isinstance(item, dict):
            continue
        frase_bruta = item.get("sentence", "")
        chave = normalizar_frase(frase_bruta)
        if not chave:
            continue
        if chave not in triplas:
            ordem.append(chave)
            frase_original[chave] = frase_bruta
            triplas[chave] = []
            vistos[chave] = set()

        sub = None
        for k in ("gold", "triples", "relations"):
            if k in item and isinstance(item[k], list):
                sub = item[k]
                break
        candidatas = sub if sub is not None else [item]

        for t in candidatas:
            if not isinstance(t, dict):
                continue
            a1 = str(t.get("arg1", "") or "")
            r = str(t.get("rel", t.get("relation", "")) or "")
            a2 = str(t.get("arg2", "") or "")
            if not (a1 or r or a2):
                continue
            assinatura = (normalizar_frase(a1), normalizar_frase(r), normalizar_frase(a2))
            if assinatura in vistos[chave]:
                continue
            vistos[chave].add(assinatura)
            triplas[chave].append({"arg1": a1, "rel": r, "arg2": a2})

    return [{"sentence": frase_original[c], "relations": triplas[c]} for c in ordem]


def carregar_agrupado(caminho: Path) -> List[dict]:
    return agrupar_por_frase(achatar(ler_todos_os_objetos_json(caminho)))


# --------------------------------------------------------------------------- #
# 2. CASAMENTO GOLD x PREDIÇÃO (exact / lexical / nenhum)
# --------------------------------------------------------------------------- #

def _overlap(a: str, b: str) -> float:
    ta, tb = set(a.lower().split()), set(b.lower().split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


def bate_lexical(g: dict, p: dict, limiar: float) -> bool:
    return (
        _overlap(g["arg1"], p["arg1"]) > limiar
        and _overlap(g["rel"], p["rel"]) > limiar
        and _overlap(g["arg2"], p["arg2"]) > limiar
    )


def bate_exact(g: dict, p: dict) -> bool:
    return (
        g["arg1"].strip().lower() == p["arg1"].strip().lower()
        and g["rel"].strip().lower() == p["rel"].strip().lower()
        and g["arg2"].strip().lower() == p["arg2"].strip().lower()
    )


def classificar_predicoes(gold: List[dict], pred: List[dict], limiar: float) -> Tuple[List[str], set]:
    """Devolve (status por tripla predita, índices do gold recuperados).
    status[i] em {"exact", "lexical", "none"}."""
    usados: set = set()
    status = [None] * len(pred)

    for i, p in enumerate(pred):
        for j, g in enumerate(gold):
            if j not in usados and bate_exact(g, p):
                status[i] = "exact"
                usados.add(j)
                break

    for i, p in enumerate(pred):
        if status[i] is not None:
            continue
        for j, g in enumerate(gold):
            if j not in usados and bate_lexical(g, p, limiar):
                status[i] = "lexical"
                usados.add(j)
                break

    status = [s or "none" for s in status]
    return status, usados


# --------------------------------------------------------------------------- #
# 3. MONTAGEM DA PLANILHA
# --------------------------------------------------------------------------- #

FONTE = "Calibri"
COR_EXATO = "1E7A34"     # verde escuro
COR_LEXICAL = "4CAF50"   # verde
COR_FALSO_POSITIVO = "C0392B"  # vermelho
COR_NAO_RECUPERADO = "C0392B"  # vermelho (gold nunca extraído por ninguém)
COR_CINZA = "888888"
COR_CONSENSO = "B8860B"      # dourado/amarelo escuro - TODOS os modelos da aba concordam, fora do gold
COR_CONSENSO_LLM = "2471A3"  # azul - só as LLMs comerciais concordam entre si, fora do gold
COR_UNANIME = "6C3483"       # roxo - TODOS os modelos da aba recuperaram essa tripla do gold

FONTE_NORMAL = InlineFont(rFont=FONTE, sz=10)
FONTE_EXATO = InlineFont(rFont=FONTE, sz=10, b=True, color=COR_EXATO)
FONTE_LEXICAL = InlineFont(rFont=FONTE, sz=10, color=COR_LEXICAL)
FONTE_FP = InlineFont(rFont=FONTE, sz=10, color=COR_FALSO_POSITIVO)
FONTE_NAO_RECUPERADO = InlineFont(rFont=FONTE, sz=10, b=True, color=COR_NAO_RECUPERADO)
FONTE_VAZIO = InlineFont(rFont=FONTE, sz=10, i=True, color=COR_CINZA)
FONTE_CONSENSO = InlineFont(rFont=FONTE, sz=10, b=True, color=COR_CONSENSO)
FONTE_CONSENSO_LLM = InlineFont(rFont=FONTE, sz=10, b=True, color=COR_CONSENSO_LLM)
FONTE_UNANIME = InlineFont(rFont=FONTE, sz=10, b=True, color=COR_UNANIME)

_PALAVRAS_LLM = ("grok", "gpt", "claude", "gemini")


def eh_llm_comercial(nome_modelo: str) -> bool:
    """Heurística: LLMs de chat comerciais (Grok/GPT/Claude/Gemini) vs.
    extratores locais/especializados (LlamaPortOIE3, PortNOIE, Qwen3OIE,
    DptOIE, PTOIE-Flair, PortugueseT5OIE, ...), pelo nome do arquivo/modelo."""
    n = nome_modelo.lower()
    return any(p in n for p in _PALAVRAS_LLM)


def montar_celula_gold(gold_triplas: List[dict], recuperadas_por_modelo: Dict[int, set],
                        total_modelos: int) -> CellRichText:
    """`recuperadas_por_modelo[i]` = conjunto de nomes de modelo que
    recuperaram (exato ou lexical) a i-ésima tripla do gold. Cada tripla é
    marcada em 3 níveis:
      ⚠  ninguém recuperou (vermelho)
      ⭐ TODOS os modelos da aba recuperaram, cada um por conta própria
         (roxo) — sinal de que é um fato "fácil"/inequívoco
      (sem marca) recuperada por alguns, não por todos
    """
    if not gold_triplas:
        return CellRichText([TextBlock(FONTE_VAZIO, "(sem triplas no gabarito)")])
    blocos = []
    for i, g in enumerate(gold_triplas):
        texto = f"{g['arg1']} → {g['rel']} → {g['arg2']}"
        if i > 0:
            blocos.append("\n")
        modelos_que_recuperaram = recuperadas_por_modelo.get(i, set())
        if not modelos_que_recuperaram:
            blocos.append(TextBlock(FONTE_NAO_RECUPERADO, f"⚠ {texto}"))
        elif total_modelos >= 2 and len(modelos_que_recuperaram) == total_modelos:
            blocos.append(TextBlock(FONTE_UNANIME, f"⭐ {texto}"))
        else:
            blocos.append(TextBlock(FONTE_NORMAL, texto))
    return CellRichText(blocos)


def montar_celula_predicao(pred_triplas: List[dict], status: List[str]) -> CellRichText:
    if not pred_triplas:
        return CellRichText([TextBlock(FONTE_VAZIO, "(nenhuma extração)")])
    blocos = []
    simbolo_fonte = {
        "exact": ("✓✓ ", FONTE_EXATO),
        "lexical": ("✓ ", FONTE_LEXICAL),
        "none": ("✗ ", FONTE_FP),
        "consenso": ("🟡 ", FONTE_CONSENSO),
        "consenso_llm": ("🔷 ", FONTE_CONSENSO_LLM),
    }
    for i, p in enumerate(pred_triplas):
        prefixo, fonte = simbolo_fonte[status[i]]
        texto = f"{prefixo}{p['arg1']} → {p['rel']} → {p['arg2']}"
        if i > 0:
            blocos.append("\n")
        blocos.append(TextBlock(fonte, texto))
    return CellRichText(blocos)


def marcar_consenso_fora_do_gold(status_por_modelo: Dict[str, Tuple[List[dict], List[str]]]) -> None:
    """Detecta, entre os falsos positivos (status == "none"), triplas em que
    vários modelos concordam entre si (mesmo arg1/rel/arg2, normalizados) mas
    que nenhum bateu com o gold. Modifica `status_por_modelo` in-place,
    trocando "none" por um dos dois níveis de concordância:

      "consenso"     — TODOS os modelos da aba (LLMs + locais/especializados)
                       extraíram a mesma tripla. Sinal mais forte de que o
                       gold pode ter perdido uma relação real.
      "consenso_llm" — só as LLMs comerciais (Grok/GPT/Claude/Gemini)
                       presentes na aba concordam entre si, mas nenhum
                       extrator local/especializado extraiu a mesma tripla.
                       Sinal mais fraco (pode ser um viés compartilhado só
                       pelas LLMs de chat, não confirmado por um extrator
                       independente).

    "consenso_llm" só é calculado quando a aba tem 2+ LLMs E pelo menos 1
    modelo local/especializado (senão a distinção entre os dois grupos não
    faz sentido). Cada assinatura é classificada no nível mais forte que
    atingir: "consenso" tem prioridade sobre "consenso_llm".
    """
    total_modelos = len(status_por_modelo)
    if total_modelos < 2:
        return

    modelos_llm = {m for m in status_por_modelo if eh_llm_comercial(m)}
    modelos_especializados = set(status_por_modelo) - modelos_llm
    checar_consenso_llm = len(modelos_llm) >= 2 and len(modelos_especializados) >= 1

    contagem: Dict[Tuple[str, str, str], set] = {}
    for nome_modelo, (pred_triplas, status) in status_por_modelo.items():
        for p, s in zip(pred_triplas, status):
            if s != "none":
                continue
            assinatura = (normalizar_frase(p["arg1"]), normalizar_frase(p["rel"]), normalizar_frase(p["arg2"]))
            contagem.setdefault(assinatura, set()).add(nome_modelo)

    assinaturas_consenso_total = {a for a, ms in contagem.items() if len(ms) == total_modelos}
    assinaturas_consenso_llm = set()
    if checar_consenso_llm:
        # Igualdade exata (não subconjunto): TODAS as LLMs concordam e
        # NENHUM modelo local/especializado propôs a mesma tripla. Um
        # subconjunto (ex.: LLMs + Qwen3OIE) não conta como "só LLMs".
        assinaturas_consenso_llm = {
            a for a, ms in contagem.items()
            if a not in assinaturas_consenso_total and ms == modelos_llm
        }

    if not assinaturas_consenso_total and not assinaturas_consenso_llm:
        return

    for nome_modelo, (pred_triplas, status) in status_por_modelo.items():
        for i, p in enumerate(pred_triplas):
            if status[i] != "none":
                continue
            assinatura = (normalizar_frase(p["arg1"]), normalizar_frase(p["rel"]), normalizar_frase(p["arg2"]))
            if assinatura in assinaturas_consenso_total:
                status[i] = "consenso"
            elif assinatura in assinaturas_consenso_llm:
                status[i] = "consenso_llm"


def gerar_aba(wb: Workbook, nome_aba: str, gold_ordenado: List[dict],
              modelos: Dict[str, Dict[str, List[dict]]], limiar: float) -> None:
    """modelos: {nome_modelo: {frase_normalizada: [triplas]}}"""
    ws = wb.create_sheet(title=nome_aba[:31])

    cabecalho = ["Frase", "Gabarito (Gold)"] + list(modelos.keys())
    ws.append(cabecalho)
    for col_idx, _ in enumerate(cabecalho, start=1):
        c = ws.cell(row=1, column=col_idx)
        c.font = Font(name=FONTE, bold=True, color="FFFFFF", size=11)
        c.fill = PatternFill("solid", start_color="2C3E50")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.freeze_panes = "C2"
    ws.row_dimensions[1].height = 22

    ws.column_dimensions["A"].width = 45
    ws.column_dimensions["B"].width = 55
    for i in range(len(modelos)):
        ws.column_dimensions[get_column_letter(3 + i)].width = 55

    for linha_idx, item_gold in enumerate(gold_ordenado, start=2):
        frase = item_gold["sentence"]
        gold_triplas = item_gold["relations"]
        chave = normalizar_frase(frase)

        recuperadas_por_modelo: Dict[int, set] = {}
        celulas_modelos: Dict[str, CellRichText] = {}
        status_por_modelo: Dict[str, Tuple[List[dict], List[str]]] = {}

        for nome_modelo, dados_modelo in modelos.items():
            pred_triplas = dados_modelo.get(chave, [])
            status, usados = classificar_predicoes(gold_triplas, pred_triplas, limiar)
            for i in usados:
                recuperadas_por_modelo.setdefault(i, set()).add(nome_modelo)
            status_por_modelo[nome_modelo] = (pred_triplas, status)

        marcar_consenso_fora_do_gold(status_por_modelo)

        ws.cell(row=linha_idx, column=1, value=frase).font = Font(name=FONTE, size=10)
        ws.cell(row=linha_idx, column=1).alignment = Alignment(wrap_text=True, vertical="top")

        c_gold = ws.cell(row=linha_idx, column=2)
        c_gold.value = montar_celula_gold(gold_triplas, recuperadas_por_modelo, len(modelos))
        c_gold.alignment = Alignment(wrap_text=True, vertical="top")

        for col_offset, (nome_modelo, (pred_triplas, status)) in enumerate(status_por_modelo.items()):
            c = ws.cell(row=linha_idx, column=3 + col_offset)
            c.value = montar_celula_predicao(pred_triplas, status)
            c.alignment = Alignment(wrap_text=True, vertical="top")

        if linha_idx % 2 == 0:
            fundo = PatternFill("solid", start_color="F5F6F7")
            for col_idx in range(1, len(cabecalho) + 1):
                ws.cell(row=linha_idx, column=col_idx).fill = fundo

    ws.auto_filter.ref = f"A1:{get_column_letter(len(cabecalho))}{len(gold_ordenado) + 1}"


# --------------------------------------------------------------------------- #
# 4. DETECÇÃO AUTOMÁTICA DA ESTRUTURA DO PROJETO
# --------------------------------------------------------------------------- #
#
# Convenção do projeto (ajuste se a sua estrutura for diferente):
#
#   <raiz>/
#     dados/<algo>gold<algo>.jsonl                    <- gold, achado por nome
#     Respostas/10_batches/Respostas <Tipo>/*.jsonl    <- um "batch" por rodada
#     Respostas/15_batches/Respostas <Tipo>/*.jsonl
#     Outputs/metricas/10_batches/                     <- saída desse batch
#     Outputs/metricas/15_batches/

_RE_PASTA_BATCH = re.compile(r"^(\d+)_batches$")


def listar_batches(raiz: Path) -> List[Path]:
    """Lista as pastas Respostas/N_batches/ existentes, ordenadas por N."""
    raiz_respostas = raiz / "Respostas"
    if not raiz_respostas.exists():
        return []
    encontrados = []
    for p in raiz_respostas.iterdir():
        if p.is_dir():
            m = _RE_PASTA_BATCH.match(p.name)
            if m:
                encontrados.append((int(m.group(1)), p))
    encontrados.sort(key=lambda x: x[0])
    return [p for _, p in encontrados]


def escolher_pasta_batch(raiz: Path, batch: str | None) -> Path:
    """Resolve qual pasta Respostas/N_batches/ usar.

    - Se --batch foi passado, usa Respostas/<batch>_batches/ (erro se não existir).
    - Se não foi passado e só existe um batch, usa ele.
    - Se não foi passado e existem vários, usa o de maior N e avisa.
    - Se não existir NENHUM Respostas/N_batches/, cai de volta para a raiz
      (compatibilidade com 'Respostas <Tipo>/' direto na raiz).
    """
    candidatos = listar_batches(raiz)

    if batch:
        alvo = raiz / "Respostas" / f"{batch}_batches"
        if alvo.exists():
            return alvo
        nomes = [p.name for p in candidatos]
        print(f"❌ Batch '{batch}' não encontrado em Respostas/. Disponíveis: {nomes or '(nenhum)'}")
        sys.exit(1)

    if not candidatos:
        return raiz

    if len(candidatos) == 1:
        return candidatos[0]

    escolhido = candidatos[-1]
    print(f"ℹ️  Múltiplos batches encontrados ({[p.name for p in candidatos]}). "
          f"Usando o mais recente: '{escolhido.name}'. Use --batch N para escolher outro.")
    return escolhido


def detectar_gold(raiz: Path) -> Path | None:
    """Procura um arquivo gold dentro de <raiz>/dados/ (nome contendo 'gold')."""
    pasta_dados = raiz / "dados"
    if not pasta_dados.exists():
        return None
    candidatos = sorted(pasta_dados.glob("*gold*.jsonl"))
    return candidatos[0] if candidatos else None


def pasta_saida_metricas(raiz: Path, pasta_batch: Path) -> Path:
    """Espelha o nome do batch dentro de Outputs/metricas/, criando se preciso."""
    destino = raiz / "Outputs" / "metricas" / pasta_batch.name
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def descobrir_pastas_de_tarefa(base: Path) -> List[Path]:
    return sorted(p for p in base.iterdir() if p.is_dir() and p.name.startswith("Respostas"))


# --------------------------------------------------------------------------- #
# 5. CLI
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser(description="Gera planilha comparativa Gold x Modelos (XLSX)")
    parser.add_argument("--gold", default=None,
                         help="Caminho do arquivo gold (.jsonl). Se omitido, detecta em dados/*gold*.jsonl")
    parser.add_argument("--pastas", nargs="*", default=None,
                         help="Pastas de tarefa (cada uma vira uma aba). Se omitido, detecta em "
                              "Respostas/N_batches/Respostas */ automaticamente.")
    parser.add_argument("--batch", default=None,
                         help="Nome do batch (ex.: '10' para Respostas/10_batches/). "
                              "Se omitido, usa o mais recente encontrado.")
    parser.add_argument("--saida", default=None,
                         help="Caminho do .xlsx de saída. Se omitido, salva em "
                              "Outputs/metricas/N_batches/comparativo_extracoes.xlsx")
    parser.add_argument("--limiar", type=float, default=0.5, help="Limiar de overlap lexical (default: 0.5)")
    parser.add_argument("--corpus", default=None, choices=list(CORPORA),
                         help="Atalho: define gold + pasta de respostas + saida pelo registro.")
    
    args = parser.parse_args()

    raiz = Path.cwd()


    if args.corpus:
        cfg = resolver_corpus(args.corpus)
        raiz_respostas = raiz / cfg['respostas']
        pasta_batch = raiz_respostas / f"{args.batch or '10'}_batches"
        args.gold = args.gold or cfg['gold']
        args.pastas = args.pastas or [str(p) for p in descobrir_pastas_de_tarefa(pasta_batch)]
        if args.saida is None:
             args.saida = str(cfg["saida"]/pasta_batch.name/ "comparativo_extracoes.xlsx")

    if args.gold:
        caminho_gold = Path(args.gold)
    else:
        caminho_gold = detectar_gold(raiz)
        if caminho_gold is None:
            print(f"❌ Não encontrei gold automaticamente em '{raiz}/dados/*gold*.jsonl'. Use --gold para indicar manualmente.")
            sys.exit(1)

    if not caminho_gold.exists():
        print(f"❌ Gold não encontrado: {caminho_gold}")
        sys.exit(1)

    if args.pastas:
        pastas = [Path(p) for p in args.pastas]
        pasta_batch = None
    else:
        pasta_batch = escolher_pasta_batch(raiz, args.batch)
        pastas = descobrir_pastas_de_tarefa(pasta_batch)
        if not pastas:
            print(f"❌ Nenhuma pasta 'Respostas *' encontrada em '{pasta_batch}'. Use --pastas para indicar manualmente.")
            sys.exit(1)

    if args.saida:
        caminho_saida = Path(args.saida)
    elif pasta_batch is not None:
        caminho_saida = pasta_saida_metricas(raiz, pasta_batch) / "comparativo_extracoes.xlsx"
    else:
        caminho_saida = Path("comparativo_extracoes.xlsx")

    print(f"Carregando gabarito: {caminho_gold} ...")
    gold_ordenado = carregar_agrupado(caminho_gold)
    print(f"-> {len(gold_ordenado)} frase(s) no gabarito.")

    wb = Workbook()
    wb.remove(wb.active)

    for pasta in pastas:
        if not pasta.exists():
            print(f"⚠️  Pasta não encontrada, pulando: {pasta}")
            continue
        arquivos_modelo = sorted(pasta.glob("*.jsonl"))
        if not arquivos_modelo:
            print(f"⚠️  Nenhum .jsonl em {pasta}, pulando.")
            continue

        print(f"\n📄 Aba: {pasta.name}")
        modelos: Dict[str, Dict[str, List[dict]]] = {}
        for caminho_modelo in arquivos_modelo:
            print(f"   Lendo modelo: {caminho_modelo.name}")
            agrupado = carregar_agrupado(caminho_modelo)
            modelos[caminho_modelo.stem] = {
                normalizar_frase(x["sentence"]): x["relations"] for x in agrupado
            }

        gerar_aba(wb, pasta.name, gold_ordenado, modelos, args.limiar)

    wb.save(caminho_saida)
    print(f"\n✅ Planilha salva em: {caminho_saida.resolve()}")
    print("   Legenda: ✓✓ = casamento exato | ✓ = casamento lexical (>50%) | ✗ = falso positivo")
    print("            🟡 = TODOS os modelos da aba (LLMs + locais/especializados) extraíram a mesma tripla, mas não está no gold")
    print("            🔷 = só as LLMs comerciais concordam entre si nessa tripla; nenhum extrator local/especializado a extraiu")
    print("            ⚠ (no gold) = tripla do gabarito nunca recuperada por nenhum modelo")
    print("            ⭐ (no gold) = tripla do gabarito recuperada por TODOS os modelos da aba, cada um por conta própria")


if __name__ == "__main__":
    main()