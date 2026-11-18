"""Roda extratores locais do Portuguese-OpenIE (FORMAS) em um corpus do pipeline, no Kaggle/Colab.

Modelos (nome no pipeline -> pasta de destino):
  Qwen3OIE_0_6B / _4B / _8B, PortugueseT5OIE_Abstractive  -> Respostas SistemasAbstrativos
  PortugueseT5OIE (T5 extrativo)                          -> Respostas SistemasExtrativos
Corpora: oiec_pt_abs, oiec_pt (100 sentenças cada, mesmo texto) e bia (262).
Saída  : um .jsonl por modelo no esquema do pipeline {"sentence": ..., "relations": [{arg1, rel, arg2}]}
         em  Respostas/<corpus>/10_batches/<pasta de destino>/   e um .zip para baixar.

COMO USAR
 1. Notebook novo. Accelerator: GPU T4 x2 (o 8B não cabe em uma T4 só). Internet: On.
 2. Suba como dataset o arquivo de sentenças do corpus: dados/<corpus>_gold_sentences.jsonl
    (oiec_pt_abs_gold_sentences.jsonl, oiec_pt_gold_sentences.jsonl ou bia_gold_sentences.jsonl).
 3. Célula 1:  !pip install -q "portuguese-openie[transformers]"
 4. Célula 2:  cole este arquivo inteiro e rode.
    Para outro corpus ou outros modelos, troque a última linha do arquivo por, por exemplo:
        main("oiec_pt_abs", ["PortugueseT5OIE"])
        main("bia", ["PortugueseT5OIE", "Qwen3OIE_0_6B"])
 5. Baixe o zip de /kaggle/working e extraia dentro de Respostas/ do repositório.

Pode ser interrompido e rodado de novo: o que já foi gravado é reaproveitado (retoma da última sentença).
"""
from __future__ import annotations

import gc
import json
import platform
import shutil
import time
import traceback
from datetime import datetime
from pathlib import Path

# --------------------------------------------------------------------------- #
# Configuração
# --------------------------------------------------------------------------- #
ABS, EXT = "Respostas SistemasAbstrativos", "Respostas SistemasExtrativos"
# nome no pipeline  ->  (identificador da biblioteca portuguese_openie, pasta de destino)
MODELOS = {
    "Qwen3OIE_0_6B": ("qwen3-oie-0.6b", ABS),
    "Qwen3OIE_4B": ("qwen3-oie-4b", ABS),
    "Qwen3OIE_8B": ("qwen3-oie-8b", ABS),
    "PortugueseT5OIE_Abstractive": ("portuguese-t5-oie-abstractive", ABS),
    "PortugueseT5OIE": ("portuguese-t5-oie", EXT),
}
N_ESPERADO = {"oiec_pt_abs": 100, "oiec_pt": 100, "bia": 262}
LOTE = 10
SAIDA = Path("/kaggle/working") if Path("/kaggle/working").exists() else Path(".")


# --------------------------------------------------------------------------- #
def achar_entrada(corpus: str) -> Path:
    nome = f"{corpus}_gold_sentences.jsonl"
    for raiz in (Path("/kaggle/input"), Path("."), Path("dados")):
        if raiz.exists():
            achados = sorted(raiz.rglob(nome))
            if achados:
                return achados[0]
    raise SystemExit(f"{nome} não encontrado. Suba-o como dataset (passo 2).")


def ler_sentencas(caminho: Path, corpus: str) -> list[str]:
    frases = [json.loads(l)["sentence"] for l in caminho.read_text(encoding="utf-8").splitlines() if l.strip()]
    esperado = N_ESPERADO.get(corpus)
    if esperado and len(frases) != esperado:
        print(f"ATENÇÃO: esperava {esperado} sentenças em {corpus}, li {len(frases)}")
    return frases


def ja_gravadas(arq: Path, frases: list[str]) -> int:
    """Quantas sentenças iniciais já estão gravadas e batem com a entrada (retomada segura)."""
    if not arq.exists():
        return 0
    n = 0
    for linha, frase in zip(arq.read_text(encoding="utf-8").splitlines(), frases):
        try:
            if json.loads(linha)["sentence"] != frase:
                break
        except Exception:
            break
        n += 1
    return n


def liberar_gpu() -> None:
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def rodar_modelo(nome: str, ident: str, pasta_destino: str, frases: list[str], corpus: str) -> dict:
    from portuguese_openie import PortugueseOpenIE

    base = SAIDA / "Respostas" / corpus / f"{LOTE}_batches"
    arq = base / pasta_destino / f"{nome}.jsonl"
    bruto = base / "_bruto_sistemas" / f"{nome}.raw.jsonl"
    arq.parent.mkdir(parents=True, exist_ok=True)
    bruto.parent.mkdir(parents=True, exist_ok=True)

    feitas = ja_gravadas(arq, frases)
    if feitas == len(frases):
        print(f"[{nome}] já completo ({feitas}/{len(frases)}), pulando")
        return {"modelo": nome, "id": ident, "status": "ja_completo"}

    modo = "w"
    if feitas > 0:                                   # retomada: mantém só as linhas válidas
        linhas = arq.read_text(encoding="utf-8").splitlines()[:feitas]
        arq.write_text("\n".join(linhas) + "\n", encoding="utf-8")
        modo = "a"
        print(f"[{nome}] retomando da sentença {feitas + 1}")

    print(f"[{nome}] carregando {ident} ...")
    t0 = time.time()
    extrator = PortugueseOpenIE(ident)               # defaults da biblioteca: device_map="auto", dtype="auto"
    print(f"[{nome}] carregado em {time.time() - t0:.0f}s")

    erros, vazias = [], 0
    with open(arq, modo, encoding="utf-8") as f, open(bruto, modo, encoding="utf-8") as fb:
        for i in range(feitas, len(frases)):
            frase = frases[i]
            relacoes, raw = [], None
            try:
                res = extrator.extract_with_metadata(frase)
                raw = res.raw_output
                for t in res.triples:
                    if t.subject and t.object:                     # triplas sem argumento não entram
                        relacoes.append({"arg1": t.subject, "rel": t.relation, "arg2": t.object})
            except Exception as e:                                  # uma sentença ruim não derruba o lote
                erros.append({"indice": i, "sentenca": frase, "erro": repr(e)})
                traceback.print_exc()
            vazias += not relacoes
            f.write(json.dumps({"sentence": frase, "relations": relacoes}, ensure_ascii=False) + "\n")
            fb.write(json.dumps({"sentence": frase, "raw_output": raw}, ensure_ascii=False) + "\n")
            f.flush(); fb.flush()
            if (i + 1) % 10 == 0:
                print(f"[{nome}] {i + 1}/{len(frases)}")

    del extrator
    liberar_gpu()
    print(f"[{nome}] pronto: {len(frases)} sentenças, {vazias} sem tripla, {len(erros)} com erro")
    return {"modelo": nome, "id": ident, "pasta": pasta_destino, "status": "ok", "sem_tripla": vazias,
            "erros": erros, "segundos": round(time.time() - t0)}


def info_ambiente() -> dict:
    info = {"data": datetime.now().isoformat(timespec="seconds"), "python": platform.python_version()}
    for pacote in ("portuguese_openie", "transformers", "torch", "accelerate"):
        try:
            info[pacote] = getattr(__import__(pacote), "__version__", "?")
        except Exception:
            info[pacote] = "não instalado"
    try:
        import torch
        info["gpus"] = [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]
    except Exception:
        info["gpus"] = []
    return info


def main(corpus: str = "oiec_pt_abs", selecionados: list[str] | None = None) -> None:
    if corpus not in N_ESPERADO:
        raise SystemExit(f"corpus desconhecido: {corpus}. Opções: {', '.join(N_ESPERADO)}")
    desconhecidos = set(selecionados or []) - set(MODELOS)
    if desconhecidos:
        raise SystemExit(f"modelo desconhecido: {sorted(desconhecidos)}. Opções: {', '.join(MODELOS)}")

    entrada = achar_entrada(corpus)
    frases = ler_sentencas(entrada, corpus)
    print("corpus:", corpus, "| entrada:", entrada, "|", len(frases), "sentenças")
    amb = info_ambiente()
    print("ambiente:", json.dumps(amb, ensure_ascii=False))

    resumo = []
    for nome, (ident, pasta) in MODELOS.items():
        if selecionados and nome not in selecionados:
            continue
        try:
            resumo.append(rodar_modelo(nome, ident, pasta, frases, corpus))
        except Exception as e:                       # ex.: 8B sem memória: registra e segue para o próximo
            traceback.print_exc()
            resumo.append({"modelo": nome, "id": ident, "status": "falhou", "erro": repr(e)})
            liberar_gpu()

    base = SAIDA / "Respostas" / corpus / f"{LOTE}_batches"
    base.mkdir(parents=True, exist_ok=True)
    (base / "info_execucao_locais.json").write_text(
        json.dumps({"corpus": corpus, "ambiente": amb, "execucao": resumo}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    zip_path = shutil.make_archive(str(SAIDA / f"respostas_locais_{corpus}"), "zip", SAIDA, f"Respostas/{corpus}")
    print("\nzip para baixar:", zip_path)
    for r in resumo:
        print(" -", r["modelo"], r["status"], r.get("sem_tripla", ""), r.get("erro", ""))


if __name__ == "__main__":
    main()
