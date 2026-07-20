"""DataSenado -- Pesquisa Nacional de Violência Doméstica e Familiar.

Cada rodada (bienal) tem um CSV de microdados e um .xlsx de dicionário,
casados pelo ano no nome. Publica um Parquet por rodada, com os códigos
já recodificados para as descrições do dicionário.

Sem fetch automatizado: a página oficial é SPA sem endpoint estático.
Arquivos ficam em MANUAL_DIR (ver env.example).
"""
import re
import sys
import logging
import unicodedata
from pathlib import Path

import pandas as pd

from scripts.common.paths import MANUAL_DATASEN_DIR, MANUAL_DATASEN_DICT_DIR
from scripts.common import exit_codes
from scripts.common.bucket_sync import carregar_manifesto, salvar_manifesto
from scripts.common.publish import dataframe_para_parquet

logger = logging.getLogger(__name__)

PASTA_BUCKET = "datasen"
CSV_GLOB = "pnvd_*.csv"
DICT_GLOB = "pnvd_dict_*.xlsx"
NOME_SAIDA = "pn_violencia_domestica_{ano}.parquet"

CSV_SEP = ";"
CSV_ENCODING = "utf-8-sig"

SLUGIFY_COLUMN_NAMES = True
SLUGIFY_VALUES = False

NO_CATEGORY_MARKERS = {"-"}
YEAR_PATTERN = re.compile(r"(\d{4})")


def extrair_ano(nome_arquivo: str) -> str | None:
    matches = YEAR_PATTERN.findall(nome_arquivo)
    return matches[-1] if matches else None


def descobrir_pares_por_ano(csv_dir: Path, dict_dir: Path) -> dict[str, tuple[Path, Path]]:
    """{ano: (csv, dicionario)} só para os anos com os dois arquivos."""
    csvs = {}
    for csv_path in sorted(csv_dir.glob(CSV_GLOB)):
        ano = extrair_ano(csv_path.stem)
        if ano:
            csvs[ano] = csv_path

    dicts = {}
    for dict_path in sorted(dict_dir.glob(DICT_GLOB)):
        ano = extrair_ano(dict_path.stem)
        if ano:
            dicts[ano] = dict_path

    apenas_csv = sorted(set(csvs) - set(dicts))
    apenas_dict = sorted(set(dicts) - set(csvs))
    if apenas_csv:
        logger.warning(f"CSV sem dicionário para {apenas_csv} -- ignorado.")
    if apenas_dict:
        logger.warning(f"Dicionário sem CSV para {apenas_dict} -- ignorado.")

    return {ano: (csvs[ano], dicts[ano]) for ano in sorted(set(csvs) & set(dicts))}


def limpar_texto(valor) -> str:
    if valor is None:
        return ""
    texto = str(valor).replace("\r", " ").replace("\n", " ").replace("\t", " ")
    return re.sub(r"\s+", " ", texto).strip()


def adaptar_descricao_variavel(desc_bruta: str) -> str:
    """Remove referências cruzadas tipo "(Ver VD_IDADE)" do nome."""
    texto = re.sub(r"\(\s*[Vv]er[^)]*\)", "", limpar_texto(desc_bruta)).strip()
    return re.sub(r"\s+", " ", texto).strip()


def padronizar_texto(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "_", texto).strip("_") or "coluna"


def normalizar_codigo(valor) -> str:
    """11, '11' e 11.0 viram a mesma chave."""
    if pd.isna(valor):
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


def ler_dicionario(dict_path: Path) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """(renomeação de colunas, mapas de código -> descrição por variável)."""
    df = pd.read_excel(dict_path, sheet_name="DICIONÁRIO", dtype=str)
    df = df.reindex(columns=[
        "Código da variável", "Descrição da variável", "Regra",
        "Código da categoria", "Descrição da categoria",
    ])

    column_rename: dict[str, str] = {}
    value_maps: dict[str, dict[str, str]] = {}
    codigo_atual = None

    for _, row in df.iterrows():
        codigo = row["Código da variável"]
        desc = row["Descrição da variável"]
        cat_codigo = row["Código da categoria"]
        cat_desc = row["Descrição da categoria"]

        codigo = codigo.strip() if isinstance(codigo, str) else codigo

        if isinstance(codigo, str) and codigo != "":
            desc_vazia = not (isinstance(desc, str) and desc.strip())
            cat_vazio = not (isinstance(cat_codigo, str) and cat_codigo.strip())
            if desc_vazia and cat_vazio:
                # cabeçalho de seção ou nota de rodapé, não é variável
                codigo_atual = None
                continue

            codigo_atual = codigo
            adaptada = adaptar_descricao_variavel(desc)
            column_rename[codigo_atual] = padronizar_texto(adaptada) if SLUGIFY_COLUMN_NAMES else adaptada
            value_maps.setdefault(codigo_atual, {})

        if codigo_atual is None:
            continue

        cat_limpo = cat_codigo.strip() if isinstance(cat_codigo, str) else cat_codigo
        if pd.isna(cat_limpo) or not cat_limpo or cat_limpo in NO_CATEGORY_MARKERS:
            continue

        cat_desc_limpa = limpar_texto(cat_desc)
        if SLUGIFY_VALUES:
            cat_desc_limpa = padronizar_texto(cat_desc_limpa)
        value_maps[codigo_atual][cat_limpo] = cat_desc_limpa

    return column_rename, {k: v for k, v in value_maps.items() if v}


def aplicar_dicionario(df: pd.DataFrame, column_rename: dict, value_maps: dict) -> pd.DataFrame:
    df = df.copy()

    # recodifica antes de renomear, enquanto o código da variável ainda
    # é o nome da coluna
    for var_codigo, mapping in value_maps.items():
        if var_codigo not in df.columns:
            continue
        df[var_codigo] = df[var_codigo].map(
            lambda v: mapping.get(normalizar_codigo(v), v) if pd.notna(v) else v
        )

    rename_final = {}
    nomes_vistos: dict[str, int] = {}
    for var_codigo in df.columns:
        novo_nome = column_rename.get(var_codigo) or var_codigo

        if novo_nome in nomes_vistos:
            nomes_vistos[novo_nome] += 1
            sufixo = padronizar_texto(var_codigo) if SLUGIFY_COLUMN_NAMES else var_codigo
            novo_nome = f"{novo_nome}_{sufixo}" if SLUGIFY_COLUMN_NAMES else f"{novo_nome} ({sufixo})"
        else:
            nomes_vistos[novo_nome] = 1

        rename_final[var_codigo] = novo_nome

    return df.rename(columns=rename_final)


def processar_ano(ano: str, csv_path: Path, dict_path: Path) -> bool:
    logger.info(f"[{ano}] Lendo dicionário: {dict_path.name}")
    column_rename, value_maps = ler_dicionario(dict_path)
    logger.info(f"[{ano}] {len(column_rename)} variáveis ({len(value_maps)} com categorias).")

    raw_df = pd.read_csv(csv_path, sep=CSV_SEP, encoding=CSV_ENCODING, dtype=str)
    logger.info(f"[{ano}] CSV bruto: {raw_df.shape[0]} linhas x {raw_df.shape[1]} colunas.")

    faltantes = set(raw_df.columns) - set(column_rename)
    if faltantes:
        logger.warning(f"[{ano}] {len(faltantes)} coluna(s) fora do dicionário, mantidas como estão: {sorted(faltantes)}")

    tratado = aplicar_dicionario(raw_df, column_rename, value_maps)
    return dataframe_para_parquet(tratado, PASTA_BUCKET, NOME_SAIDA.format(ano=ano))


def main() -> int:
    if not MANUAL_DATASEN_DIR.exists():
        logger.error(f"{MANUAL_DATASEN_DIR} não existe.")
        return exit_codes.ERRO

    pares = descobrir_pares_por_ano(MANUAL_DATASEN_DIR, MANUAL_DATASEN_DICT_DIR)
    if not pares:
        logger.error(
            f"Nenhum par CSV/dicionário encontrado ('{CSV_GLOB}' em {MANUAL_DATASEN_DIR}, "
            f"'{DICT_GLOB}' em {MANUAL_DATASEN_DICT_DIR})."
        )
        return exit_codes.ERRO

    manifesto = carregar_manifesto(PASTA_BUCKET)
    processados, falhas, pulados = [], [], []

    for ano, (csv_path, dict_path) in pares.items():
        tamanhos = {
            csv_path.name.upper(): csv_path.stat().st_size,
            dict_path.name.upper(): dict_path.stat().st_size,
        }
        if all(manifesto.get(k) == v for k, v in tamanhos.items()):
            pulados.append(ano)
            continue

        try:
            if processar_ano(ano, csv_path, dict_path):
                manifesto.update(tamanhos)
                processados.append(ano)
            else:
                falhas.append(ano)
        except Exception as e:
            logger.error(f"[{ano}] Falha: {e}")
            falhas.append(ano)

    if pulados:
        logger.info(f"[SKIP] Sem mudança: {pulados}")

    if processados:
        salvar_manifesto(PASTA_BUCKET, manifesto)
        logger.info(f"Publicados: {processados}")

    if falhas:
        logger.error(f"Falhas: {falhas}")
        return exit_codes.ERRO

    return exit_codes.SUCESSO if processados else exit_codes.SEM_NOVIDADE


if __name__ == "__main__":
    sys.exit(main())