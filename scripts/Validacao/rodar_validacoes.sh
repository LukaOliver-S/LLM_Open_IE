#!/usr/bin/env bash
# Roda TODAS as validações para os corpora/tarefas.
# Uso:  bash scripts/Validacao/rodar_tudo.sh
set -u

# raiz do projeto = pasta_do_script/../..  (o .sh mora em scripts/Validacao/)
RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$RAIZ" || { echo "ERRO: não consegui ir pra raiz do projeto"; exit 1; }
if [ ! -d "scripts/Validacao" ]; then
  echo "ERRO: 'scripts/Validacao' não existe em $(pwd). Salve o .sh dentro de scripts/Validacao/."
  exit 1
fi

# python da venv; se não existir, tenta o 'python' do PATH (venv ativada)
PY=".venv/Scripts/python.exe"
[ -x "$PY" ] || PY="python"
X="-X utf8"

echo ">> raiz: $(pwd)"
echo ">> python: $PY"

CORPORA=("bia" "oiec_pt")                  # inclua "unified" quando coletar
TAREFAS=("abstractive" "dpto" "oiec" "ptoiedp")

for C in "${CORPORA[@]}"; do
  echo ""
  echo "########## CORPUS: $C ##########"
  "$PY" $X scripts/Validacao/resultados.py           --corpus "$C" || echo "  [skip resultados $C]"
  "$PY" $X scripts/Validacao/resultados_por_campo.py --corpus "$C" || echo "  [skip por_campo $C]"
  "$PY" $X scripts/Validacao/contagem_triplas.py     --corpus "$C" || echo "  [skip contagem $C]"
  "$PY" $X scripts/Validacao/comparação_batches.py   --corpus "$C" || echo "  [skip batches $C]"
  "$PY" $X scripts/Validacao/checagem_consenso.py    --corpus "$C" || echo "  [skip consenso $C]"
  "$PY" $X scripts/Validacao/graficos_resumo.py      --corpus "$C" || echo "  [skip resumo $C]"
  # gerar_graficos usa os CSVs que o resultados.py acabou de gerar (não usa --corpus)
  "$PY" $X scripts/Validacao/gerar_graficos.py Outputs/metricas/"$C"/*/resultados_*.csv || echo "  [skip graficos $C]"
  for T in "${TAREFAS[@]}"; do
    echo "----- $C / $T -----"
    "$PY" $X scripts/Validacao/rodar_carb.py     --corpus "$C" --tarefa "$T" --ic || echo "  [skip carb $C/$T]"
    "$PY" $X scripts/Validacao/bootstrap_carb.py --corpus "$C" --tarefa "$T"       || echo "  [skip boot $C/$T]"
  done
done
echo ""
echo "FEITO."
