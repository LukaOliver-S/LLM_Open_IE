import json
from pathlib import Path

# Caminho do arquivo que você acabou de filtrar
caminho_entrada = Path(r"C:\Users\ADM\LLM_Open_IE\dados\oiec_pt_gold_sentences_filtrado.jsonl")
# Caminho para o novo arquivo limpo
caminho_saida = caminho_entrada.with_name("oiec_pt_gold_sentences_limpo.jsonl")

print(f"Simplificando sentenças de: {caminho_entrada.name}")

count = 0
with open(caminho_entrada, 'r', encoding='utf-8') as f_in, \
     open(caminho_saida, 'w', encoding='utf-8') as f_out:
    
    for linha in f_in:
        if not linha.strip():
            continue
            
        data = json.loads(linha)
        
        # Cria a nova estrutura apenas com a chave 'sentence'
        novo_objeto = {"sentence": data.get("sentence", "")}
        
        # Escreve a linha no novo arquivo
        f_out.write(json.dumps(novo_objeto, ensure_ascii=False) + '\n')
        count += 1

print(f"Concluído! {count} sentenças processadas.")
print(f"Arquivo salvo em: {caminho_saida}")