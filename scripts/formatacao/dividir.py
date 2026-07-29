import argparse
import math
import os

def dividir_jsonl(caminho_entrada, num_partes, pasta_base='sentencas'):
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

        # Cria a pasta de saída (ex: sentencas/10_sentencas, ou sentencas_oiecpt/10_sentencas)
        pasta_saida = os.path.join(pasta_base, f'{num_partes}_sentencas')
        os.makedirs(pasta_saida, exist_ok=True)

        # Gera os novos arquivos
        for i in range(num_partes):
            inicio = i * linhas_por_arquivo
            fim = inicio + linhas_por_arquivo
            pedaco = linhas[inicio:fim]

            # Se não houver mais linhas para processar, interrompe o loop
            if not pedaco:
                break

            # Cria o nome do arquivo de saída (ex: sentencas/10_sentencas/sentencas_parte_1.jsonl)
            nome_saida = os.path.join(pasta_saida, f"sentencas_parte_{i+1}.jsonl")
            
            with open(nome_saida, 'w', encoding='utf-8') as f_out:
                f_out.writelines(pedaco)
                
            print(f"Criado: {nome_saida} (contém {len(pedaco)} sentenças)")
            
    except FileNotFoundError:
        print(f"Erro: O arquivo '{caminho_entrada}' não foi encontrado.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--entrada", default="dados/apenas_sentencas.jsonl",
                         help="Arquivo de sentenças a dividir (um JSON por linha).")
    parser.add_argument("--lotes", type=int, default=25, help="Número de partes/lotes.")
    parser.add_argument("--saida-base", default="sentencas",
                         help="Pasta base onde criar '<lotes>_sentencas/' (ex.: 'sentencas_oiecpt' para um corpus diferente).")
    args = parser.parse_args()

    dividir_jsonl(args.entrada, args.lotes, args.saida_base)