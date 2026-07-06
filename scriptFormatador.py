import json


arquivo_entrada = 'bia_gold_sentences.jsonl' 
arquivo_saida = 'apenas_sentencas.jsonl' 

def extrair_sentencas_para_jsonl(caminho_entrada, caminho_saida):
    try:
      
        with open(caminho_entrada, 'r', encoding='utf-8') as f_in, \
             open(caminho_saida, 'w', encoding='utf-8') as f_out:
            
            contagem = 0
            for linha in f_in:
              
                if linha.strip():
                   
                    dados = json.loads(linha)
                    
                  
                    sentenca = dados.get('sentence', '')
                    
                    if sentenca:
                        
                        novo_json = {"sentence": sentenca}
                        
                      
                        f_out.write(json.dumps(novo_json, ensure_ascii=False) + '\n')
                        contagem += 1
                        
        print(f"Sucesso! {contagem} sentenças foram extraídas para '{caminho_saida}'.")
        
    except FileNotFoundError:
        print(f"Erro: O arquivo '{caminho_entrada}' não foi encontrado.")
    except json.JSONDecodeError:
        print("Erro: Falha ao interpretar o arquivo. Certifique-se de que cada linha é um JSON válido.")


extrair_sentencas_para_jsonl(arquivo_entrada, arquivo_saida)