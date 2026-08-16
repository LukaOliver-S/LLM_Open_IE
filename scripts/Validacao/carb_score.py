# scripts/Validacao/carb_score.py
"""
Port fiel do scorer CaRB (Bhardwaj et al., EMNLP 2019 — repo dair-iitd/CaRB),
adaptado para PT-BR e para extrações SEM score de confiança (LLMs via chat).

Fidelidade ao original:
  - precisão: matching guloso 1-para-1 maximizando precisão (igual carb.py)
  - recall:   cada gold casa com seu MELHOR pred (muitos-para-1) (igual carb.py)
  - match token-level via linient_tuple_match / binary_linient_tuple_match
Adaptações (aprovar):
  - be-forms EN -> formas de ser/estar PT (FORMAS_SER)
  - said-verbs EN -> verbos de dizer PT (VERBOS_DIZER)
  - SEM remoção de stopwords (o CaRB usava lista inglesa)
"""
from __future__ import annotations
from copy import copy
import re

# ---- listas localizadas (APROVAR/AJUSTAR) ----
FORMAS_SER = {"ser","é","e","era","eram","foi","foram","sendo","sido","são","sao",
              "seja","sejam","for","fosse","estar","está","esta","estava","estão","estao"}
VERBOS_DIZER = {"disse","dizer","diz","afirmou","afirma","declarou","declara",
                "acrescentou","acrescenta","contou","conta","informou","informa"}

def tokens(texto: str) -> list[str]:
    """lower + split; tira pontuação nas bordas de cada token. (ignoreCase do CaRB)"""
    return [t for t in re.findall(r"[\wÀ-ÿ]+", (texto or "").lower())]

class Tripla:
    """pred = relação; args = [arg1, arg2] (vazios finais removidos)."""
    __slots__ = ("pred", "args")
    def __init__(self, arg1: str, rel: str, arg2: str, manter_arg2_vazio=False):
        self.pred = rel
        args = [arg1, arg2]
        if not manter_arg2_vazio:
            while args and not (args[-1] or "").strip():
                args.pop()               # arg2 vazio -> vira tripla de 1 arg (CaRB zera)
        self.args = args

# ---------- match token-level (port fiel de linient_tuple_match) ----------
def linient_tuple_match(ref: Tripla, ex: Tripla):
    precision = [0, 0]; recall = [0, 0]
    predicted_words = tokens(ex.pred)
    gold_words = tokens(ref.pred)
    precision[1] += len(predicted_words); recall[1] += len(gold_words)

    matching = 0
    for w in gold_words:
        if w in predicted_words:
            matching += 1; predicted_words.remove(w)
    # equivalente ao 'be' do CaRB: formas de ser/estar contam como match
    if (set(predicted_words) & FORMAS_SER) and (set(gold_words) & FORMAS_SER):
        for w in list(predicted_words):
            if w in FORMAS_SER:
                matching += 1; predicted_words.remove(w); break

    if matching == 0:
        return [0.0, 0.0]
    precision[0] += matching; recall[0] += matching

    for i in range(len(ref.args)):
        gold_words = tokens(ref.args[i]); recall[1] += len(gold_words)
        if len(ex.args) <= i:
            if i < 2: return [0.0, 0.0]      # precisa dos 2 primeiros args
            else: continue
        predicted_words = tokens(ex.args[i]); precision[1] += len(predicted_words)
        matching = 0
        for w in gold_words:
            if w in predicted_words:
                matching += 1; predicted_words.remove(w)
        precision[0] += matching; recall[0] += matching

    prec = precision[0] / precision[1] if precision[1] else 0.0
    rec  = recall[0] / recall[1] if recall[1] else 0.0
    return [prec, rec]

def binary_linient_tuple_match(ref: Tripla, ex: Tripla):
    r = ref
    if len(ref.args) >= 2:
        r = copy(ref); r.args = [ref.args[0], " ".join(ref.args[1:])]
    e = ex
    if len(ex.args) >= 2:
        e = copy(ex); e.args = [ex.args[0], " ".join(ex.args[1:])]
    direto = linient_tuple_match(r, e)
    # relações de dizer: CaRB tenta a ordem invertida dos args e pega o melhor
    if set(tokens(ref.pred)) & VERBOS_DIZER and len(ex.args) >= 2:
        e2 = copy(ex); e2.args = [" ".join(ex.args[1:]), ex.args[0]]
        return max(direto, linient_tuple_match(r, e2))
    return direto

# ---------- pontuação por sentença (ponto único, sem confiança) ----------
def score_sentenca(gold_trs, pred_trs):
    """Retorna (prec_num, prec_den, rec_num, rec_den) — acumuladores decomponíveis."""
    ng, npr = len(gold_trs), len(pred_trs)
    scores = [[binary_linient_tuple_match(g, p) for p in pred_trs] for g in gold_trs]

    # recall: cada gold -> melhor pred (muitos-para-1)
    rec_num = sum(max((scores[i][j][1] for j in range(npr)), default=0.0)
                  for i in range(ng))
    # precisão: guloso 1-para-1 maximizando precisão
    prec_num = 0.0; sel_r, sel_c = set(), set()
    for _ in range(min(ng, npr)):
        melhor, br, bc = -1.0, -1, -1
        for i in range(ng):
            if i in sel_r: continue
            for j in range(npr):
                if j in sel_c: continue
                if scores[i][j][0] > melhor:
                    melhor, br, bc = scores[i][j][0], i, j
        if br < 0: break
        sel_r.add(br); sel_c.add(bc); prec_num += scores[br][bc][0]
    return prec_num, npr, rec_num, ng

def agregar(acumuladores):
    """acumuladores: lista de (pn, pd, rn, rd). Retorna P/R/F1 do CaRB."""
    Pn = sum(a[0] for a in acumuladores); Pd = sum(a[1] for a in acumuladores)
    Rn = sum(a[2] for a in acumuladores); Rd = sum(a[3] for a in acumuladores)
    P = Pn / Pd if Pd else 1.0
    R = Rn / Rd if Rd else 0.0
    F = 2 * P * R / (P + R) if (P + R) else 0.0
    return dict(precision=P, recall=R, f1=F)