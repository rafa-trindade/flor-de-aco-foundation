"""Orquestrador do pipeline: extract + process de todas as fontes.

Sequencial de propósito: fontes que compartilham pasta_bucket também
compartilham o _manifest.json, e gravá-lo em paralelo corrompe o controle
de novidade.

Uso:
    python -m scripts.run_all
    python -m scripts.run_all --so datasus_sim,ibge
    python -m scripts.run_all --pular datasus_sinan
    python -m scripts.run_all --process-only
    python -m scripts.run_all --force-load
    python -m scripts.run_all --no-load

Cada extract termina em um de três estados (ver scripts/common/exit_codes.py).
O process só roda quando o extract reportou dado novo -- reprocessar o SIM
inteiro sem necessidade custa dezenas de minutos.

O load só roda quando alguma fonte AUTOMÁTICA trouxe novidade nesta execução.
Fonte manual não tem como reportar isso: use --force-load depois de atualizar
os arquivos em MANUAL_DIR.
"""
import argparse
import importlib.util
import subprocess
import sys
import time

from scripts.common import exit_codes
from scripts.config.fontes import FONTES, Fonte

ROTULO = {
    exit_codes.SUCESSO: "✔ SUCESSO",
    exit_codes.SEM_NOVIDADE: "= SEM NOVIDADE",
    exit_codes.ERRO: "✖ ERRO",
}

LOAD_MODULES = [
    "scripts.process.process_metadados",
    "scripts.kaggle.load_to_kaggle",
]


def validar_registro() -> list[str]:
    """Módulos registrados em fontes.py que não existem.

    Renomear um script sem atualizar o registro já quebrou 3 das 4 fontes
    aqui; falhar no início é melhor que descobrir no meio da execução.
    """
    return [
        m
        for f in FONTES
        for m in f.extract_modules + f.process_modules
        if importlib.util.find_spec(m) is None
    ]


def rodar_modulo(modulo: str) -> int:
    """Roda em subprocess, como `python -m`.

    Subprocess e não runpy: os scripts chamam sys.exit e configuram estado
    global, o que num mesmo processo contamina as execuções seguintes.
    """
    print(f"\n[{modulo}]")
    return subprocess.run([sys.executable, "-m", modulo]).returncode


def rodar_fonte(fonte: Fonte, pular_extract: bool) -> dict:
    print(f"\n{'=' * 70}")
    print(f"{fonte.nome} ({fonte.id})")
    print('=' * 70)
    if fonte.nota:
        print(f"Nota: {fonte.nota}")

    extract = exit_codes.SEM_NOVIDADE
    novidade_confiavel = False

    if not fonte.automatica:
        print("[MANUAL] Sem extract automatizado -- assume que MANUAL_DIR já está atualizado.")
    elif pular_extract:
        print("[PULADO] extract (--process-only).")
    else:
        codigos = [rodar_modulo(m) for m in fonte.extract_modules]
        for m, c in zip(fonte.extract_modules, codigos):
            print(f"[extract] {m} -> {ROTULO.get(c, f'código {c}')}")
        if exit_codes.ERRO in codigos:
            extract = exit_codes.ERRO
        elif exit_codes.SUCESSO in codigos:
            extract = exit_codes.SUCESSO
            novidade_confiavel = True

    if extract == exit_codes.ERRO:
        print("[PULADO] process não roda -- extract falhou.")
        return {"id": fonte.id, "extract": extract, "process": exit_codes.SEM_NOVIDADE,
                "novidade": False}

    # Fonte manual e --process-only não têm como reportar novidade, então
    # o process roda e decide sozinho (via manifesto) se há o que fazer.
    deve_processar = (
        extract == exit_codes.SUCESSO
        or not fonte.automatica
        or pular_extract
    )
    if not deve_processar:
        print("[PULADO] process não roda -- nada novo desde a última execução.")
        return {"id": fonte.id, "extract": extract, "process": exit_codes.SEM_NOVIDADE,
                "novidade": False}

    process = exit_codes.SEM_NOVIDADE
    for m in fonte.process_modules:
        c = rodar_modulo(m)
        print(f"[process] {m} -> {ROTULO.get(c, f'código {c}')}")
        if c == exit_codes.ERRO:
            process = exit_codes.ERRO
        elif c == exit_codes.SUCESSO and process != exit_codes.ERRO:
            process = exit_codes.SUCESSO

    return {"id": fonte.id, "extract": extract, "process": process,
            "novidade": novidade_confiavel or process == exit_codes.SUCESSO}


def main():
    parser = argparse.ArgumentParser(description="Orquestrador do pipeline flor-de-aco-foundation")
    parser.add_argument("--so", help="Lista de ids ou pastas de bucket, separados por vírgula")
    parser.add_argument("--pular", help="Lista de ids ou pastas de bucket a ignorar")
    parser.add_argument("--process-only", action="store_true", help="Pula o extract")
    parser.add_argument("--force-load", action="store_true",
                        help="Roda o load mesmo sem novidade (após atualizar fonte manual)")
    parser.add_argument("--no-load", action="store_true", help="Nunca roda o load")
    args = parser.parse_args()

    faltando = validar_registro()
    if faltando:
        print("[FATAL] Módulos registrados em fontes.py que não existem:")
        for m in faltando:
            print(f"  {m}")
        sys.exit(1)

    fontes = list(FONTES)
    if args.so:
        alvos = {x.strip() for x in args.so.split(",")}
        fontes = [f for f in fontes if f.id in alvos or f.pasta_bucket in alvos]
    if args.pular:
        excluir = {x.strip() for x in args.pular.split(",")}
        fontes = [f for f in fontes if f.id not in excluir and f.pasta_bucket not in excluir]

    if not fontes:
        print("[AVISO] Nenhuma fonte corresponde aos filtros.")
        return

    print(f"Rodando {len(fontes)} fonte(s): {', '.join(f.id for f in fontes)}")

    inicio = time.time()
    resultados = []
    try:
        for f in fontes:
            resultados.append(rodar_fonte(f, pular_extract=args.process_only))
    except KeyboardInterrupt:
        print("\n\n[INTERROMPIDO] Ctrl+C. Seguro rodar de novo: cada fonte pula o que já está feito.")

    horas, resto = divmod(time.time() - inicio, 3600)
    minutos, segundos = divmod(resto, 60)

    print(f"\n\n{'=' * 70}")
    print(f"RESUMO -- {len(resultados)} de {len(fontes)} fonte(s) em "
          f"{int(horas)}h{int(minutos):02d}m{int(segundos):02d}s")
    print('=' * 70)
    for r in resultados:
        print(f"  {r['id']:16s} extract={ROTULO.get(r['extract'], '?'):16s} "
              f"process={ROTULO.get(r['process'], '?')}")

    houve_erro = any(r["extract"] == exit_codes.ERRO or r["process"] == exit_codes.ERRO
                     for r in resultados)
    houve_novidade = any(r["novidade"] for r in resultados)

    if args.no_load:
        print("\n[LOAD] Pulado (--no-load).")
    elif houve_erro:
        print("\n[LOAD] Pulado -- alguma fonte falhou; não publica dado possivelmente incompleto.")
    elif not (houve_novidade or args.force_load):
        print("\n[LOAD] Pulado -- nenhuma novidade nesta execução. "
              "Use --force-load se atualizou uma fonte manual.")
    else:
        print(f"\n{'=' * 70}\nLOAD (metadados + Kaggle)\n{'=' * 70}")
        for m in LOAD_MODULES:
            if rodar_modulo(m) == exit_codes.ERRO:
                houve_erro = True

    if houve_erro:
        print("\n[AVISO] Pelo menos uma etapa falhou -- revise o log acima.")
        sys.exit(1)


if __name__ == "__main__":
    main()