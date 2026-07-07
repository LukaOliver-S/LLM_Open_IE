import math
import os

# Defina o nome do seu arquivo gerado no passo anterior
arquivo_entrada = 'apenas_sentencas.jsonl'
numero_de_partes = 10

def dividir_jsonl(caminho_entrada, num_partes):
    try:
        # Lê todas as linhas do arquivo original
        with open(caminho_entrada, 'r', encoding='utf-8') as f:
            linhas = f.readlines()
        
        total_linhas = len(linhas)
        if total_linhas == 0:
            print("O arquivo está vazio!")
            return
            
        # Calcula quantas linhas cada arquivo vai ter (arredondando para cima)
        linhas_por_arquivo = math.ceil(total_linhas / num_partes)
        
        print(f"Total de linhas: {total_linhas}.")
        print(f"Dividindo em {num_partes} arquivos com até {linhas_por_arquivo} sentenças cada.\n")
        
        # Gera os novos arquivos
        for i in range(num_partes):
            inicio = i * linhas_por_arquivo
            fim = inicio + linhas_por_arquivo
            pedaco = linhas[inicio:fim]
            
            # Se não houver mais linhas para processar, interrompe o loop
            if not pedaco:
                break
                
            # Cria o nome do arquivo de saída (ex: sentencas_parte_1.jsonl)
            nome_saida = f"sentencas_parte_{i+1}.jsonl"
            
            with open(nome_saida, 'w', encoding='utf-8') as f_out:
                f_out.writelines(pedaco)
                
            print(f"Criado: {nome_saida} (contém {len(pedaco)} sentenças)")
            
    except FileNotFoundError:
        print(f"Erro: O arquivo '{caminho_entrada}' não foi encontrado.")

dividir_jsonl(arquivo_entrada, numero_de_partes)