import json
from pathlib import Path

# Caminhos dos arquivos
caminho_entrada = Path(r"C:\Users\ADM\LLM_Open_IE\dados\oiec_pt_gold_sentences.jsonl")
# Cria um novo arquivo com o sufixo '_filtrado' na mesma pasta
caminho_saida = caminho_entrada.with_name(f"{caminho_entrada.stem}_filtrado{caminho_entrada.suffix}")

linhas_mantidas = 0
linhas_removidas = 0

print(f"Lendo o arquivo: {caminho_entrada}")

with open(caminho_entrada, 'r', encoding='utf-8') as f_in, \
     open(caminho_saida, 'w', encoding='utf-8') as f_out:
    
    for linha in f_in:
        # Ignora linhas em branco
        if not linha.strip():
            continue
            
        objeto_json = json.loads(linha)
        
        # Verifica se a chave 'gold' existe e se a lista NÃO está vazia
        if "gold" in objeto_json and len(objeto_json["gold"]) > 0:
            # Salva o objeto novamente no formato JSONL
            f_out.write(json.dumps(objeto_json, ensure_ascii=False) + '\n')
            linhas_mantidas += 1
        else:
            linhas_removidas += 1

print("\n--- Concluído! ---")
print(f"Sentenças com 'gold' preenchido (mantidas): {linhas_mantidas}")
print(f"Sentenças com 'gold' vazio (removidas): {linhas_removidas}")
print(f"Novo arquivo salvo em: {caminho_saida}")