#!/usr/bin/env python3
"""
Orquestrador do pipeline: roda extract + process de todas as fontes
registradas em scripts/config/fontes.py, em sequência.

Uso:
    python3 run_all.py                 # roda tudo (extract + process)
    python3 run_all.py --only mjsp     # roda só uma fonte
    python3 run_all.py --process-only  # pula o extract, só reprocessa
    python3 run_all.py --skip-manual   # (padrão) não tenta rodar fontes manuais

Fontes marcadas como `automatica=False` (DataSenado, PNS/IBGE) não têm
extract automatizado -- este script avisa que precisam de atualização
manual em vez de tentar rodar algo que não existe.
"""
import argparse
import importlib
import sys
import traceback

from scripts.config.fontes import FONTES, Fonte


def _run_module(module_path: str) -> bool:
    """Importa um módulo e chama seu main(), se existir."""
    print(f"  -> {module_path}")
    try:
        mod = importlib.import_module(module_path)
        if hasattr(mod, "main"):
            mod.main()
        # Scripts que só rodam via `if __name__ == "__main__"` (sem função
        # main() exposta) já executam no import -- nada a mais a fazer aqui.
        return True
    except Exception:
        print(f"  [ERRO] Falha em {module_path}:")
        traceback.print_exc()
        return False


def rodar_fonte(fonte: Fonte, pular_extract: bool) -> bool:
    print(f"\n{'=' * 70}\n{fonte.nome} ({fonte.id})\n{'=' * 70}")

    if not fonte.automatica:
        print(f"[MANUAL] Esta fonte não tem extract automatizado.")
        if fonte.nota:
            print(f"  Nota: {fonte.nota}")
        print(f"  Rodando só o(s) process, assumindo que os dados brutos já foram atualizados manualmente.")
    elif fonte.nota:
        print(f"  Nota: {fonte.nota}")

    ok = True

    if fonte.automatica and not pular_extract:
        for mod in fonte.extract_modules:
            ok = _run_module(mod) and ok

    for mod in fonte.process_modules:
        ok = _run_module(mod) and ok

    print(f"{'OK' if ok else 'COM FALHAS'}: {fonte.id}")
    return ok


def main():
    parser = argparse.ArgumentParser(description="Orquestrador do pipeline flor-de-aco-foundation")
    parser.add_argument("--only", help="Roda só a fonte com este id (ver scripts/config/fontes.py)")
    parser.add_argument("--process-only", action="store_true", help="Pula o extract, roda só o process")
    args = parser.parse_args()

    alvo = [f for f in FONTES if f.id == args.only] if args.only else FONTES
    if args.only and not alvo:
        print(f"Fonte '{args.only}' não encontrada. Fontes disponíveis: {[f.id for f in FONTES]}")
        sys.exit(1)

    resultados = {f.id: rodar_fonte(f, pular_extract=args.process_only) for f in alvo}

    print(f"\n{'=' * 70}\nResumo\n{'=' * 70}")
    for id_fonte, ok in resultados.items():
        print(f"  {'✔' if ok else '✘'} {id_fonte}")

    if not all(resultados.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()