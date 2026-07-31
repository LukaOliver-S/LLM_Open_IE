import json, re

def chave(s):
    # remove TODOS os espaços + caixa -> neutraliza a re-tokenização do DptOIE
    return re.sub(r"\s+", "", str(s)).lower()

# 1) mapa: chave-sem-espaço -> texto EXATO da sentença do gold
gold = [json.loads(l) for l in open("dados/bia_gold_sentences.jsonl", encoding="utf-8") if l.strip()]
mapa = {chave(g["sentence"]): g["sentence"] for g in gold}

# 2) corrige as sentenças do DPTOIE-PY
f = "Respostas/10_batches/Respostas ExtrativoDPTO-IE/respostaDPTOIE-PY.jsonl"
regs = [json.loads(l) for l in open(f, encoding="utf-8") if l.strip()]

corrigidos = nao_encontrados = 0
for r in regs:
    k = chave(r["sentence"])
    if k in mapa:
        if r["sentence"] != mapa[k]:
            r["sentence"] = mapa[k]     # troca pelo texto exato do gold
            corrigidos += 1
    else:
        nao_encontrados += 1

print("corrigidas:", corrigidos, "| ainda sem par no gold:", nao_encontrados)

# 3) regrava o arquivo
with open(f, "w", encoding="utf-8") as out:
    for r in regs:
        out.write(json.dumps(r, ensure_ascii=False) + "\n")