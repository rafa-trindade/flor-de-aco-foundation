#!/usr/bin/env python3
"""
Orquestrador do pipeline: roda extract + process de todas as fontes
registradas em scripts/config/fontes.py, em sequência.

Uso:
    python3 run_all.py                 # roda tudo (extract + process + load, se houver novidade)
    python3 run_all.py --only mjsp     # roda só uma fonte; load roda se ELA tiver novidade
    python3 run_all.py --process-only  # pula o extract, só reprocessa
    python3 run_all.py --force-load    # força load mesmo sem novidade (ex: após atualizar fonte manual)
    python3 run_all.py --no-load       # nunca roda load_to_bucket/load_to_kaggle

Fontes marcadas como `automatica=False` (DataSenado, PNS/IBGE) não têm
extract automatizado -- este script avisa que precisam de atualização
manual em vez de tentar rodar algo que não existe.

O load (scripts/load/load_to_bucket.py + scripts/kaggle/load_to_kaggle.py)
só roda automaticamente quando pelo menos uma fonte AUTOMÁTICA reportou
dado novo de verdade nesta execução -- evita recriar uma versão nova no
Kaggle toda vez que o pipeline roda sem nenhuma mudança real.

CONTRATO DE 3 ESTADOS (ver scripts/common/exit_codes.py):
Um extract pode terminar de 3 jeitos: sucesso com dado novo, sucesso sem
nada de novo, ou erro. O process só roda no primeiro caso -- não faz
sentido reprocessar (às vezes caro, como a conversão .dbc -> parquet do
SIM) quando nada mudou desde a última execução. Scripts que não usam
scripts.common.exit_codes (ex: macroregiao, mjsp) são tratados como
"sempre com novidade" por padrão -- comportamento igual ao de antes.
"""
import argparse
import runpy
import sys
import traceback

from scripts.config.fontes import FONTES, Fonte
from scripts.common import exit_codes

SUCESSO, SEM_NOVIDADE, ERRO = "sucesso", "sem_novidade", "erro"


def _run_module(module_path: str) -> str:
    """
    Executa um módulo exatamente como `python -m module_path` executaria --
    via runpy, com run_name="__main__". Isso garante que o bloco
    `if __name__ == "__main__":` do script rode de verdade, independente de
    o script expor uma função main() ou só ter código solto nesse bloco
    (a maioria dos scripts do projeto é do segundo tipo).

    Retorna SUCESSO, SEM_NOVIDADE ou ERRO -- lido do exit code do script,
    se ele usar scripts.common.exit_codes; senão assume SUCESSO (mesmo
    comportamento de antes, pra não quebrar scripts que não adotaram o
    contrato de 3 estados ainda).
    """
    print(f"  -> {module_path}")
    try:
        runpy.run_module(module_path, run_name="__main__")
        return SUCESSO
    except SystemExit as e:
        codigo = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        if codigo == exit_codes.SUCESSO:
            return SUCESSO
        elif codigo == exit_codes.SEM_NOVIDADE:
            return SEM_NOVIDADE
        else:
            print(f"  [ERRO] {module_path} terminou com exit code {codigo}")
            return ERRO
    except Exception:
        print(f"  [ERRO] Falha em {module_path}:")
        traceback.print_exc()
        return ERRO


def rodar_fonte(fonte: Fonte, pular_extract: bool) -> tuple[bool, bool]:
    """Retorna (ok, teve_novidade_confiavel).

    teve_novidade_confiavel só é True quando um extract automático
    reportou SUCESSO de verdade (dado novo). Fontes manuais ou rodadas
    com --process-only não contam pra essa flag -- não tem como saber se
    o dado bruto mudou sem um extract rodando."""
    print(f"\n{'=' * 70}\n{fonte.nome} ({fonte.id})\n{'=' * 70}")

    if not fonte.automatica:
        print(f"[MANUAL] Esta fonte não tem extract automatizado.")
        if fonte.nota:
            print(f"  Nota: {fonte.nota}")
        print(f"  Rodando só o(s) process, assumindo que os dados brutos já foram atualizados manualmente.")
    elif fonte.nota:
        print(f"  Nota: {fonte.nota}")

    houve_erro = False
    houve_novidade = True       # default: roda o process (fonte manual ou extract pulado)
    novidade_confiavel = False  # só True quando um extract automático confirmou

    if fonte.automatica and not pular_extract:
        resultados = [_run_module(mod) for mod in fonte.extract_modules]
        houve_erro = ERRO in resultados
        houve_novidade = any(r == SUCESSO for r in resultados)
        novidade_confiavel = houve_novidade

    if houve_erro:
        print(f"[PULADO] process não roda -- extract falhou.")
    elif not houve_novidade:
        print(f"[PULADO] process não roda -- nenhum dado novo desde a última execução.")
    else:
        for mod in fonte.process_modules:
            if _run_module(mod) == ERRO:
                houve_erro = True

    ok = not houve_erro
    print(f"{'OK' if ok else 'COM FALHAS'}: {fonte.id}")
    return ok, novidade_confiavel


LOAD_MODULES = [
    "scripts.load.load_to_bucket",
    "scripts.kaggle.load_to_kaggle",
]


def main():
    parser = argparse.ArgumentParser(description="Orquestrador do pipeline flor-de-aco-foundation")
    parser.add_argument("--only", help="Roda só a fonte com este id (ver scripts/config/fontes.py)")
    parser.add_argument("--process-only", action="store_true", help="Pula o extract, roda só o process")
    parser.add_argument(
        "--force-load",
        action="store_true",
        help="Roda load_to_bucket/load_to_kaggle mesmo sem novidade detectada "
             "(útil depois de atualizar uma fonte manual, ex: DataSenado)",
    )
    parser.add_argument(
        "--no-load",
        action="store_true",
        help="Nunca roda load_to_bucket/load_to_kaggle, mesmo com novidade",
    )
    args = parser.parse_args()

    alvo = [f for f in FONTES if f.id == args.only] if args.only else FONTES
    if args.only and not alvo:
        print(f"Fonte '{args.only}' não encontrada. Fontes disponíveis: {[f.id for f in FONTES]}")
        sys.exit(1)

    resultados = {f.id: rodar_fonte(f, pular_extract=args.process_only) for f in alvo}

    print(f"\n{'=' * 70}\nResumo\n{'=' * 70}")
    for id_fonte, (ok, _) in resultados.items():
        print(f"  {'✔' if ok else '✘'} {id_fonte}")

    sucesso_geral = all(ok for ok, _ in resultados.values())
    houve_mudanca_real = any(novidade for _, novidade in resultados.values())

    if args.no_load:
        print("\n[LOAD] Pulado (--no-load).")
    elif not sucesso_geral:
        print("\n[LOAD] Pulado -- pelo menos uma fonte falhou, não publica dado possivelmente incompleto.")
    elif not (houve_mudanca_real or args.force_load):
        print(
            "\n[LOAD] Pulado -- nenhuma fonte automática reportou dado novo nesta execução. "
            "Se você atualizou uma fonte manual (DataSenado, PNS/IBGE), rode de novo com --force-load."
        )
    else:
        print(f"\n{'=' * 70}\nLoad (bucket + Kaggle)\n{'=' * 70}")
        for mod in LOAD_MODULES:
            resultado = _run_module(mod)
            if resultado == ERRO:
                sucesso_geral = False

    if not sucesso_geral:
        sys.exit(1)


if __name__ == "__main__":
    main()