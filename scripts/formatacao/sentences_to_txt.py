import json

# Lê o gold (262 frases; cada objeto tem o campo "sentence")
gold = [json.loads(l) for l in open("dados/oiec_pt_apenas_sentencas.jsonl", encoding="utf-8") if l.strip()]

# Escreve UMA frase por linha — é exatamente o formato que o DptOIE espera no -it txt.
# newline="\n" força quebra de linha estilo Linux (evita problema de CRLF no Colab).
# o .replace remove quebras internas pra não partir uma frase em duas linhas.
with open("dados/sentencas_100.txt", "w", encoding="utf-8", newline="\n") as f:
    for g in gold:
        s = g["sentence"].replace("\r", " ").replace("\n", " ").strip()
        f.write(s + "\n")

print(f"{len(gold)} frases escritas em dados/sentencas_100.txt")