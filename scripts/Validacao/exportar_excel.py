#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
exportar_excel.py
==================

Consolida os resultados que o pipeline já gerou em UM arquivo Excel, para consulta e apresentação.
Não recalcula nada: lê os CSVs de Outputs/ e organiza em abas. Rode antes `rodar_tudo.py`, para os CSVs estarem
atualizados.

ABAS
  LEIA-ME                     fontes, definições das métricas e a lista de arquivos excluídos das tabelas por cobertura baixa
  F1 lexical / F1 exato       LLM (linhas) x prompt (colunas), um bloco por corpus, com escala de cor
  Cobertura                   % das sentenças do gold que cada resposta cobre (explica células em branco)
  Resultados completos        todas as linhas de resultados_*.csv (LLMs e sistemas locais), com cobertura
  Bootstrap IC                F1 com IC 95% por bootstrap de sentenças
  Prompt vs SemRegras         diferença de F1 de cada prompt contra o sem regras, com IC pareado
  Dif vs lider                cada sistema contra o de maior F1
  Triplas por frase           volume de triplas geradas contra o gold
  Por campo                   precisão, recall e F1 de arg1, rel e arg2
  Variantes                   pares de triplas em comprimentos diferentes do mesmo argumento (gold e respostas)
  Correlacao resumo/pontos    triplas geradas por tripla do gold contra F1, precisão e recall
  Pronomes e transitividade   argumentos só de pronome e triplas transitivas
  Corpus                      características do gold de cada corpus (volume, tamanho dos campos, pronomes, variantes...)
  FP em sentencas vazias      falsos positivos que caem em sentenças que o gold deixa sem tripla
  Consenso                    % dos falsos positivos de cada sistema que outro sistema também gerou (mesmo prompt)
  Heatmap triplas / consenso  sistema x prompt com escala de cor, incluindo os extratores locais
  Concordancia                matriz sistema x sistema (LLMs com SemRegras, extratores locais e gold)
  Indice                      lista todas as abas com link

Este arquivo tem só os valores numéricos. A planilha qualitativa (uma linha por frase, gold e modelos lado a lado) é outro
arquivo, Outputs/comparativo_extracoes.xlsx, gerado por `python gerar_planilha_comparativa.py --todos`. Para anexá-la a
este arquivo mesmo assim, use --com-qualitativo.

REGRA DE COBERTURA. Nas abas de pivô, um arquivo de resposta que cobre menos de --cobertura-minima (padrão 95%) das
sentenças do gold fica em branco, porque o recall dele estaria subestimado por coleta incompleta e não por qualidade.
As demais abas mostram tudo, com a coluna de cobertura ao lado.

USO (da raiz do repositório)
    python scripts/Validacao/exportar_excel.py
    python scripts/Validacao/exportar_excel.py --corpus bia oiec_pt --saida Outputs/resultados_consolidados.xlsx
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.hyperlink import Hyperlink

sys.path.insert(0, str(Path(__file__).resolve().parent))
from grafico_prompts_ic import ORDEM_PROMPTS, ROTULO  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
FONTE = "Arial"
PASTAS_LOCAIS = {"SistemasExtrativos", "SistemasAbstrativos"}
COL_PCT = re.compile(r"^(precisao|recall|f1|prec_|ic95|dif|largura|pct_|cobertura)")
ROTULO_LLM = {"Claude_Sonnet5": "Claude Sonnet 5", "GeminiHydrogen4": "Gemini Hydrogen 4", "Grok4.0Fast": "Grok 4.0 Fast",
              "gpt5.5_mini": "GPT-5.5 mini", "Gemini3.1Pro": "Gemini 3.1 Pro"}


def canon(modelo: str) -> str:
    return re.sub(r"^respostas?_?", "", str(modelo))


def ler(caminho: Path, **extra) -> pd.DataFrame:
    if not caminho.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(caminho)
    except pd.errors.EmptyDataError:        # CSV vazio (ex.: prompt_vs_semregras sem SemRegras no corpus)
        return pd.DataFrame()
    for k, v in extra.items():
        df.insert(0, k, v)
    return df


def juntar(partes: list[pd.DataFrame]) -> pd.DataFrame:
    partes = [p for p in partes if len(p)]
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


# ---------------------------------------------------------------------------------------------------- leitura
def filtrar(df: pd.DataFrame, col: str, ignorar: list) -> pd.DataFrame:
    if len(df) and col in df.columns and ignorar:
        return df[~df[col].isin(ignorar)].reset_index(drop=True)
    return df


def carregar(corpus: str, lotes: int, cob_min: float, ignorar: list) -> dict:
    metr = RAIZ / "Outputs" / "metricas" / corpus / f"{lotes}_batches"
    boot = RAIZ / "Outputs" / "bootstrap" / corpus
    ana = RAIZ / "Outputs" / "analise_regras" / corpus
    d: dict = {}

    res = []
    for f in sorted(metr.glob("resultados_Respostas_*.csv")):
        pasta = f.stem[len("resultados_Respostas_"):]
        if pasta in ignorar:
            continue
        res.append(ler(f, corpus=corpus, pasta=pasta))
    r = juntar(res)
    if len(r):
        r["llm"] = r["modelo"].map(canon)
        r["cobertura"] = 1 - r["n_gold_sem_cobertura"] / r["n_frases_gold"]
        r["completo"] = r["cobertura"] >= cob_min
    d["resultados"] = r

    cont = []
    for f in sorted(metr.glob("contagem_triplas_Respostas_*.csv")):
        if f.stem[len("contagem_triplas_Respostas_"):] in ignorar:
            continue
        cont.append(ler(f, corpus=corpus, pasta=f.stem[len("contagem_triplas_Respostas_"):]))
    d["triplas"] = juntar(cont)

    campo = []
    for f in sorted(metr.glob("resultados_por_campo_Respostas_*.csv")):
        if f.stem[len("resultados_por_campo_Respostas_"):] in ignorar:
            continue
        campo.append(ler(f, corpus=corpus, pasta=f.stem[len("resultados_por_campo_Respostas_"):]))
    d["campo"] = juntar(campo)

    for nome, arq in [("ic", "ic_lexical.csv"), ("ic_exact", "ic_exact.csv"), ("pv", "prompt_vs_semregras_lexical.csv"),
                      ("lider", "diferencas_vs_lider_lexical.csv")]:
        d[nome] = filtrar(filtrar(ler(boot / arq), "pasta", ignorar), "prompt", ignorar)
    d["corr_resumo"] = ler(ana / "correlacao_triplas_f1_resumo.csv")
    d["corr_pontos"] = filtrar(ler(ana / "correlacao_triplas_f1_pontos.csv"), "prompt", ignorar)
    d["variantes"] = filtrar(ler(ana / f"variantes_{lotes}_batches.csv"), "pasta", ignorar)
    d["pronomes"] = filtrar(ler(ana / f"pronomes_transitividade_{lotes}_batches.csv"), "pasta", ignorar)
    d["corpus_caract"] = ler(ana / "caracteristicas_corpus.csv")
    d["fp_vazias"] = filtrar(ler(ana / f"fp_sentencas_vazias_{lotes}_batches.csv"), "pasta", ignorar)
    cons = []
    for f in sorted((metr / "consenso").glob("resumo_consenso_Respostas_*.csv")):
        pasta = f.stem[len("resumo_consenso_Respostas_"):]
        if pasta not in ignorar:
            cons.append(ler(f, corpus=corpus, pasta=pasta))
    d["consenso"] = juntar(cons)
    d["concordancia"] = ler(ana / "concordancia_sistemas.csv")
    d["conc_agregada"] = ler(ana / "concordancia_llm_agregada.csv")
    d["distribuicao"] = filtrar(ler(ana / f"distribuicao_triplas_{lotes}_batches.csv"), "pasta", ignorar)
    return d


# ---------------------------------------------------------------------------------------------------- escrita
def estilo_cabecalho(ws, linha: int, n_cols: int, col_ini: int = 1) -> None:
    for c in range(col_ini, col_ini + n_cols):
        cel = ws.cell(row=linha, column=c)
        cel.font = Font(name=FONTE, bold=True, color="FFFFFF", size=10)
        cel.fill = PatternFill("solid", fgColor="404040")
        cel.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def escrever_df(ws, df: pd.DataFrame, linha: int = 1) -> int:
    """Escreve df a partir de `linha`, formata e devolve a próxima linha livre."""
    if df.empty:
        ws.cell(row=linha, column=1, value="(sem dados: rode os scripts que geram este CSV)").font = Font(name=FONTE, italic=True)
        return linha + 2
    for j, nome in enumerate(df.columns, start=1):
        ws.cell(row=linha, column=j, value=str(nome))
    estilo_cabecalho(ws, linha, len(df.columns))
    for i, row in enumerate(df.itertuples(index=False), start=linha + 1):
        for j, v in enumerate(row, start=1):
            if pd.isna(v):
                v = None
            elif hasattr(v, "item"):
                v = v.item()
            cel = ws.cell(row=i, column=j, value=v)
            cel.font = Font(name=FONTE, size=10)
            nome = str(df.columns[j - 1])
            if isinstance(v, float):
                cel.number_format = "0.0%" if COL_PCT.match(nome) else "0.00"
    return linha + len(df) + 2


def ajustar(ws, largura_max: int = 42) -> None:
    for col in ws.columns:
        letra = get_column_letter(col[0].column)
        maior = max((len(str(c.value)) for c in col if c.value is not None), default=8)
        ws.column_dimensions[letra].width = min(largura_max, max(10, maior + 2))


def aba_tabela(wb, titulo: str, df: pd.DataFrame) -> None:
    ws = wb.create_sheet(titulo)
    escrever_df(ws, df)
    if len(df):
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
    ajustar(ws)


def pivo(wb, titulo: str, dados: dict, col_valor: str, formato: str, usar_cobertura: bool, escala: bool) -> None:
    ws = wb.create_sheet(titulo)
    linha = 1
    for corpus, d in dados.items():
        r = d["resultados"]
        ws.cell(row=linha, column=1, value=f"Corpus {corpus}").font = Font(name=FONTE, bold=True, size=12)
        linha += 1
        if r.empty:
            ws.cell(row=linha, column=1, value="(sem resultados)").font = Font(name=FONTE, italic=True)
            linha += 2
            continue
        r = r[~r["pasta"].isin(PASTAS_LOCAIS)].copy()
        if usar_cobertura:
            r = r[r["completo"]]
        prompts = [p for p in ORDEM_PROMPTS if p in set(r["pasta"])]
        extras = sorted(set(r["pasta"]) - set(prompts))
        prompts += extras
        llms = sorted(set(r["llm"]))
        ws.cell(row=linha, column=1, value="LLM")
        for j, p in enumerate(prompts, start=2):
            ws.cell(row=linha, column=j, value=ROTULO.get(p, p))
        estilo_cabecalho(ws, linha, len(prompts) + 1)
        topo = linha + 1
        for i, m in enumerate(llms, start=topo):
            ws.cell(row=i, column=1, value=ROTULO_LLM.get(m, m)).font = Font(name=FONTE, bold=True, size=10)
            for j, p in enumerate(prompts, start=2):
                sub = r[(r["pasta"] == p) & (r["llm"] == m)]
                cel = ws.cell(row=i, column=j, value=float(sub[col_valor].iloc[0]) if len(sub) else None)
                cel.number_format = formato
                cel.font = Font(name=FONTE, size=10)
                cel.alignment = Alignment(horizontal="center")
        base = topo + len(llms) - 1
        if escala and len(llms):
            rng = f"B{topo}:{get_column_letter(len(prompts) + 1)}{base}"
            ws.conditional_formatting.add(rng, ColorScaleRule(start_type="min", start_color="F8D7D3",
                                                              mid_type="percentile", mid_value=50, mid_color="FFFFFF",
                                                              end_type="max", end_color="C6E5C3"))
        linha = base + 3
    ws.column_dimensions["A"].width = 22
    for c in range(2, 12):
        ws.column_dimensions[get_column_letter(c)].width = 17
    ws.row_dimensions[1].height = 18


ORDEM_LLM = ["Claude_Sonnet5", "GeminiHydrogen4", "Grok4.0Fast", "gpt5.5_mini", "Gemini3.1Pro"]
REGUA_RAZAO = ColorScaleRule(start_type="num", start_value=0.5, start_color="9DB8E8", mid_type="num", mid_value=1,
                             mid_color="FFFFFF", end_type="num", end_value=3, end_color="F2A66B")
REGUA_PCT = ColorScaleRule(start_type="num", start_value=0, start_color="FFFFFF", end_type="num", end_value=100, end_color="7FD0CC")


def pivo_heat(wb, titulo: str, dados: dict, chave: str, col_valor: str, formato: str, regua, nota: str) -> None:
    """Heatmap sistema x prompt. LLMs preenchem as colunas de prompt, extratores locais a coluna 'Sem prompt'.
    Células de respostas com cobertura abaixo do mínimo ficam em branco."""
    ws = wb.create_sheet(titulo)
    linha = 1
    for corpus, d in dados.items():
        src, res = d[chave], d["resultados"]
        ws.cell(row=linha, column=1, value=f"Corpus {corpus}").font = Font(name=FONTE, bold=True, size=12)
        ws.cell(row=linha, column=3, value=nota).font = Font(name=FONTE, italic=True, size=9)
        linha += 1
        if src.empty or res.empty:
            ws.cell(row=linha, column=1, value="(sem dados)").font = Font(name=FONTE, italic=True)
            linha += 3
            continue
        ok = set(zip(res[res["completo"]]["pasta"], res[res["completo"]]["modelo"]))
        s = src[[(a, b) in ok for a, b in zip(src["pasta"], src["modelo"])]].copy()
        s["llm"] = s["modelo"].map(canon)
        local = s["pasta"].isin(PASTAS_LOCAIS)
        prompts = [p for p in ORDEM_PROMPTS if p in set(s[~local]["pasta"])]
        prompts += sorted(set(s[~local]["pasta"]) - set(prompts))
        llms = [m for m in ORDEM_LLM if m in set(s[~local]["llm"])] + sorted(set(s[~local]["llm"]) - set(ORDEM_LLM))
        locais = sorted(set(s[local]["llm"]))
        cab = ["Sistema"] + [ROTULO.get(p, p) for p in prompts] + ["Sem prompt (local)"]
        for j, nome in enumerate(cab, start=1):
            ws.cell(row=linha, column=j, value=nome)
        estilo_cabecalho(ws, linha, len(cab))
        topo = linha + 1
        for i, m in enumerate(llms + locais, start=topo):
            eh_local = m in locais
            ws.cell(row=i, column=1, value=ROTULO_LLM.get(m, m)).font = Font(name=FONTE, bold=True, size=10)
            for j in range(2, len(cab) + 1):
                cel = ws.cell(row=i, column=j)
                cel.number_format = formato
                cel.font = Font(name=FONTE, size=10)
                cel.alignment = Alignment(horizontal="center")
                if j == len(cab):
                    sub_ = s[local & (s["llm"] == m)] if eh_local else s.iloc[0:0]
                else:
                    sub_ = s[(~local) & (s["llm"] == m) & (s["pasta"] == prompts[j - 2])] if not eh_local else s.iloc[0:0]
                if len(sub_):
                    cel.value = float(sub_[col_valor].iloc[0])
        base = topo + len(llms) + len(locais) - 1
        ws.conditional_formatting.add(f"B{topo}:{get_column_letter(len(cab))}{base}", regua)
        linha = base + 3
    ws.column_dimensions["A"].width = 22
    for c in range(2, 12):
        ws.column_dimensions[get_column_letter(c)].width = 14


def matriz_concordancia(wb, dados: dict) -> None:
    ws = wb.create_sheet("Concordancia")
    linha = 1
    for corpus, d in dados.items():
        c = d["concordancia"]
        if c.empty:
            continue
        ws.cell(row=linha, column=1, value=f"Corpus {corpus}: % das triplas da linha que a coluna também gerou").font = Font(name=FONTE, bold=True, size=12)
        linha += 1
        nomes = sorted(set(c["a"]) | set(c["b"]), key=lambda x: (x == "Gold", x not in ORDEM_LLM, ORDEM_LLM.index(x) if x in ORDEM_LLM else 0, x))
        ws.cell(row=linha, column=1, value="Linha / coluna")
        for j, n in enumerate(nomes, start=2):
            ws.cell(row=linha, column=j, value=ROTULO_LLM.get(n, n))
        estilo_cabecalho(ws, linha, len(nomes) + 1)
        topo = linha + 1
        idx = {(r.a, r.b): r.pct for r in c.itertuples()}
        for i, a_ in enumerate(nomes, start=topo):
            ws.cell(row=i, column=1, value=ROTULO_LLM.get(a_, a_)).font = Font(name=FONTE, bold=True, size=10)
            for j, b_ in enumerate(nomes, start=2):
                cel = ws.cell(row=i, column=j, value=float(idx[(a_, b_)]) * 100 if (a_, b_) in idx else None)
                cel.number_format = "0"
                cel.font = Font(name=FONTE, size=10)
                cel.alignment = Alignment(horizontal="center")
        base = topo + len(nomes) - 1
        ws.conditional_formatting.add(f"B{topo}:{get_column_letter(len(nomes) + 1)}{base}", REGUA_PCT)
        linha = base + 3
    ws.column_dimensions["A"].width = 22
    for k in range(2, 14):
        ws.column_dimensions[get_column_letter(k)].width = 13


ROTULOS_ABA = {"SemRegras": "Sem regras", "ExtrativoDPTO-IE": "DPTO-IE", "ExtrativoOIEC-PT": "OIEC-PT",
               "ExtrativoOIEC-PT-simples": "OIEC-PT simples", "ExtrativoPTOIE-DP": "PTOIE-DP", "ExtrativoBIA-completo": "BIA",
               "SistemasExtrativos": "Extratores locais", "AbstractiveOpenIE": "Abstr. LLMs",
               "SistemasAbstrativos": "Abstr. locais"}
DESCRICAO_ABAS = {
    "LEIA-ME": "Como ler as métricas, limites e arquivos excluídos por cobertura baixa.",
    "F1 lexical": "F1 lexical por LLM e prompt, com escala de cor.",
    "F1 exato": "F1 exato por LLM e prompt, com escala de cor.",
    "Cobertura": "% das sentenças do gold cobertas por cada resposta.",
    "Heatmap triplas": "Triplas geradas por tripla do gold, por sistema e prompt (inclui extratores locais).",
    "Heatmap consenso": "% dos falsos positivos que outro sistema também gerou, por sistema e prompt.",
    "Concordancia": "Matriz sistema x sistema: % das triplas da linha que a coluna também gerou.",
    "Resultados completos": "Precisão, recall e F1 (lexical e exato) de todos os sistemas.",
    "Bootstrap IC": "F1 com intervalo de confiança de 95% por bootstrap de sentenças.",
    "Prompt vs SemRegras": "Diferença de F1 de cada prompt contra o sem regras, com IC pareado.",
    "Dif vs lider": "Cada sistema contra o de maior F1 do corpus.",
    "Triplas por frase": "Volume de triplas geradas contra o gold.",
    "Por campo": "Precisão, recall e F1 de arg1, rel e arg2.",
    "Variantes": "Pares da mesma relação com argumentos de tamanhos diferentes.",
    "Correlacao resumo": "Correlação entre triplas geradas por tripla do gold e F1, precisão e recall.",
    "Correlacao pontos": "Pontos usados na correlação.",
    "Pronomes e transitividade": "Argumentos só de pronome e triplas transitivas, e o efeito no F1.",
    "Corpus": "Características do gold de cada corpus.",
    "FP em sentencas vazias": "Falsos positivos em sentenças que o gold deixa sem tripla.",
    "Consenso": "Consenso dos falsos positivos, por sistema e prompt.",
    "Perfil de triplas": "% de sentenças com 0, 1, 2 e 3 ou mais triplas, por sistema (gold na linha GOLD).",
    "Concordancia LLM x locais": "% das triplas de cada LLM (somando os 5 prompts) que cada extrator local e o gold também têm.",
}


def aba_indice(wb, qualitativas: list) -> None:
    """Lista todas as abas com descrição e link. Fica logo depois do LEIA-ME."""
    ws = wb.create_sheet("Indice")
    ws.append(["Aba", "O que mostra"])
    estilo_cabecalho(ws, 1, 2)
    desc_q = {t: f"Planilha qualitativa: uma linha por frase, gold e modelos lado a lado (pasta {pasta})." for t, pasta in qualitativas}
    for nome in wb.sheetnames:
        if nome == "Indice":
            continue
        ws.append([nome, DESCRICAO_ABAS.get(nome) or desc_q.get(nome, "")])
        cel = ws.cell(row=ws.max_row, column=1)
        cel.hyperlink = Hyperlink(ref=cel.coordinate, location=f"'{nome}'!A1", display=nome)    # link interno
        cel.font = Font(name=FONTE, size=10, color="0563C1", underline="single")
        ws.cell(row=ws.max_row, column=2).font = Font(name=FONTE, size=10)
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 110
    ws.freeze_panes = "A2"
    wb.move_sheet(ws, offset=1 - wb.index(ws))


def aba_leiame(wb, dados: dict, cob_min: float, lotes: int) -> None:
    ws = wb.active
    ws.title = "LEIA-ME"
    linhas = [
        ("Resultados consolidados: Open IE em português", "t"),
        (f"Gerado em {date.today().isoformat()} por scripts/Validacao/exportar_excel.py a partir dos CSVs de Outputs/. "
         f"Configuração: {lotes} lotes, métricas lexical e exata.", ""),
        ("", ""),
        ("Como ler", "h"),
        ("F1, precisão e recall lexicais: uma tripla prevista acerta uma do gold quando cada campo (arg1, rel, arg2) tem sobreposição de tokens maior que 0,5, "
         "com casamento guloso de 1 para 1. As métricas exatas exigem texto idêntico.", ""),
        ("Bootstrap: sorteia sentenças com reposição (as mesmas para todos os sistemas, então as diferenças são pareadas) e recalcula o F1. "
         "O intervalo de 95% são os percentis 2,5 e 97,5. Intervalo que inclui zero significa que a diferença não é distinguível, não que os sistemas são iguais.", ""),
        ("Os extratores locais (SistemasExtrativos) não têm prompt e aparecem só nas abas completas, não nos pivôs.", ""),
        ("O prompt BIA simples (pasta ExtrativoBIA) foi deixado de fora por decisão do grupo. Para incluí-lo, rode com --ignorar sem valores.", ""),
        ("Nos pivôs e gráficos, o rótulo BIA corresponde à pasta ExtrativoBIA-completo. As abas completas mostram o nome da pasta.", ""),
        ("Este arquivo reúne só os valores numéricos. A comparação frase a frase (gold e modelos lado a lado) está em comparativo_extracoes.xlsx. "
         "A aba Indice lista todas as abas com link.", ""),
        ("", ""),
        ("Regra de cobertura", "h"),
        (f"Nas abas F1 lexical e F1 exato, respostas que cobrem menos de {cob_min:.0%} das sentenças do gold ficam em branco, "
         "porque o recall delas está subestimado por coleta incompleta. A aba Cobertura mostra o percentual de cada uma.", ""),
    ]
    excl = []
    for corpus, d in dados.items():
        r = d["resultados"]
        if len(r):
            for _, x in r[(~r["completo"]) & (~r["pasta"].isin(PASTAS_LOCAIS))].iterrows():
                excl.append(f"{corpus} | {x['pasta']} | {x['modelo']} | cobertura {x['cobertura']:.1%}")
    linhas.append(("Arquivos abaixo da cobertura mínima:" if excl else "Todos os arquivos atingem a cobertura mínima.", "b"))
    linhas += [("  " + e, "") for e in excl]
    linhas += [
        ("", ""),
        ("Limites", "h"),
        ("Uma coleta por modelo e prompt, sem medida de variação entre execuções.", ""),
        ("Os prompts diferem em mais de uma coisa (regras, exemplos e reforço de formato), então a diferença entre dois prompts nem sempre separa a causa.", ""),
        ("O gold de cada corpus segue convenções próprias, e o avaliador premia quem gera a mesma proposição em vários comprimentos de argumento (aba Variantes).", ""),
        ("O Gemini Hydrogen 4 não tem versão documentada.", ""),
    ]
    for i, (texto, tipo) in enumerate(linhas, start=1):
        c = ws.cell(row=i, column=1, value=texto)
        c.font = Font(name=FONTE, size=14 if tipo == "t" else 11 if tipo in ("h", "b") else 10, bold=tipo in ("t", "h", "b"))
        c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.column_dimensions["A"].width = 130


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", nargs="*", default=["bia", "oiec_pt", "oiec_pt_abs"])
    ap.add_argument("--lotes", type=int, default=10)
    ap.add_argument("--cobertura-minima", type=float, default=0.95)
    ap.add_argument("--saida", default="Outputs/resultados_consolidados.xlsx")
    ap.add_argument("--ignorar", nargs="*", default=["ExtrativoBIA"],
                    help="pastas de prompt a deixar de fora (padrão: BIA simples). Use --ignorar sem valores para incluir tudo.")
    ap.add_argument("--com-qualitativo", action="store_true",
                    help="inclui também as abas qualitativas (corpus | prompt). Por padrão elas ficam no arquivo separado "
                         "comparativo_extracoes.xlsx, gerado por gerar_planilha_comparativa.py --todos")
    a = ap.parse_args()

    dados = {c: carregar(c, a.lotes, a.cobertura_minima, a.ignorar) for c in a.corpus}
    wb = Workbook()
    aba_leiame(wb, dados, a.cobertura_minima, a.lotes)
    pivo(wb, "F1 lexical", dados, "f1_lexical", "0.0%", True, True)
    pivo(wb, "F1 exato", dados, "f1_exact", "0.0%", True, True)
    pivo(wb, "Cobertura", dados, "cobertura", "0%", False, False)
    pivo_heat(wb, "Heatmap triplas", dados, "triplas", "razao_pred_gold", "0.00", REGUA_RAZAO,
              "Triplas geradas por tripla do gold. Azul: menos que o gold. Laranja: mais.")
    pivo_heat(wb, "Heatmap consenso", dados, "consenso", "pct_com_consenso", "0", REGUA_PCT,
              "% dos falsos positivos que outro sistema com o mesmo prompt também gerou.")
    matriz_concordancia(wb, dados)

    def todos(chave: str, ordenar: list[str] | None = None) -> pd.DataFrame:
        df = juntar([d[chave] for d in dados.values()])
        return df.sort_values(ordenar) if len(df) and ordenar else df

    res = todos("resultados")
    if len(res):
        cols = ["corpus", "pasta", "modelo", "llm", "n_frases_gold", "n_frases_pred", "cobertura", "completo", "precisao_lexical",
                "recall_lexical", "f1_lexical", "precisao_exact", "recall_exact", "f1_exact", "n_erros_parsing",
                "n_pred_sem_match", "n_gold_sem_cobertura"]
        res = res[[c for c in cols if c in res.columns]].sort_values(["corpus", "pasta", "f1_lexical"], ascending=[True, True, False])
    aba_tabela(wb, "Resultados completos", res)
    aba_tabela(wb, "Bootstrap IC", todos("ic"))
    aba_tabela(wb, "Prompt vs SemRegras", todos("pv"))
    aba_tabela(wb, "Dif vs lider", todos("lider"))
    aba_tabela(wb, "Triplas por frase", todos("triplas"))
    aba_tabela(wb, "Por campo", todos("campo"))
    aba_tabela(wb, "Variantes", todos("variantes"))
    aba_tabela(wb, "Correlacao resumo", todos("corr_resumo"))
    aba_tabela(wb, "Correlacao pontos", todos("corr_pontos"))
    aba_tabela(wb, "Pronomes e transitividade", todos("pronomes"))
    aba_tabela(wb, "Corpus", todos("corpus_caract"))
    aba_tabela(wb, "FP em sentencas vazias", todos("fp_vazias"))
    aba_tabela(wb, "Consenso", todos("consenso"))
    aba_tabela(wb, "Perfil de triplas", todos("distribuicao"))
    aba_tabela(wb, "Concordancia LLM x locais", todos("conc_agregada"))

    qualitativas: list = []
    if a.com_qualitativo:
        sys.path.insert(0, str(RAIZ))
        import gerar_planilha_comparativa as gpc
        ign = [f"Respostas {x}" for x in a.ignorar]
        for c in a.corpus:
            qualitativas += gpc.adicionar_abas_corpus(wb, c, str(a.lotes), ign, 0.5, ROTULOS_ABA, RAIZ)
    aba_indice(wb, qualitativas)

    saida = RAIZ / a.saida
    saida.parent.mkdir(parents=True, exist_ok=True)
    wb.save(saida)
    print("gravado:", saida)
    print("abas:", ", ".join(wb.sheetnames))


if __name__ == "__main__":
    main()
