import re
import sys
import logging
import unicodedata
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ======================================================================
# CONFIG
# ======================================================================

THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = THIS_FILE.parents[3]

LANDING_DIR = PROJECT_ROOT / "data" / "processed" / "datasen" / "raw"
DICT_DIR = LANDING_DIR / "dict"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed" / "datasen"

CSV_GLOB_PATTERN = "pnvd_*.csv"
DICT_GLOB_PATTERN = "pnvd_dict_*.xlsx"
OUTPUT_FILENAME_TEMPLATE = "pnvd_violencia_dom_{year}.csv"

CSV_SEP = ";"
CSV_ENCODING = "utf-8-sig"

# Nomes de coluna em snake_case (sem acento, minúsculo, "_" no lugar de
# espaço/pontuação). Valores das categorias mantêm o texto original do
# dicionário por padrão.
SLUGIFY_COLUMN_NAMES = True
SLUGIFY_VALUES = False

NO_CATEGORY_MARKERS = {"-"}
YEAR_PATTERN = re.compile(r"(\d{4})")


# ======================================================================
# Descoberta dos pares CSV <-> dicionário, por ano
# ======================================================================

def extrair_ano(nome_arquivo: str) -> str | None:
    """Pega o último grupo de 4 dígitos no nome do arquivo (o ano)."""
    matches = YEAR_PATTERN.findall(nome_arquivo)
    return matches[-1] if matches else None


def descobrir_pares_por_ano(landing_dir: Path, dict_dir: Path) -> dict[str, tuple[Path, Path]]:
    """Varre landing_dir e dict_dir e retorna {ano: (csv_path, dict_path)}
    apenas para os anos que têm CSV e dicionário casados."""
    csvs = {}
    for csv_path in sorted(landing_dir.glob(CSV_GLOB_PATTERN)):
        ano = extrair_ano(csv_path.stem)
        if ano:
            csvs[ano] = csv_path

    dicts = {}
    for dict_path in sorted(dict_dir.glob(DICT_GLOB_PATTERN)):
        ano = extrair_ano(dict_path.stem)
        if ano:
            dicts[ano] = dict_path

    pares = {ano: (csvs[ano], dicts[ano]) for ano in sorted(set(csvs) & set(dicts))}

    apenas_csv = sorted(set(csvs) - set(dicts))
    apenas_dict = sorted(set(dicts) - set(csvs))
    if apenas_csv:
        logger.warning(f"CSV sem dicionário correspondente para o(s) ano(s) {apenas_csv} -> ignorado(s).")
    if apenas_dict:
        logger.warning(f"Dicionário sem CSV correspondente para o(s) ano(s) {apenas_dict} -> ignorado(s).")

    return pares


# ======================================================================
# Normalização de texto
# ======================================================================

def limpar_texto(valor) -> str:
    """Normaliza espaços/tabs/quebras de linha de um texto do dicionário."""
    if valor is None:
        return ""
    texto = str(valor)
    texto = texto.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def adaptar_descricao_variavel(desc_bruta: str) -> str:
    """Adapta a descrição da variável para servir como nome de coluna,
    removendo notas de referência cruzada tipo "(Ver VD_IDADE)"."""
    texto = limpar_texto(desc_bruta)
    texto = re.sub(r"\(\s*[Vv]er[^)]*\)", "", texto).strip()
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def padronizar_texto(texto: str) -> str:
    """Remove acentos, deixa minúsculo e troca tudo que não é letra/número
    por '_' (sem '_' duplicado ou nas pontas)."""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower()
    texto = re.sub(r"[^a-z0-9]+", "_", texto).strip("_")
    return texto or "coluna"


def normalizar_codigo(valor) -> str:
    """Normaliza um código de categoria para string comparável (trata
    11, '11' e 11.0 como equivalentes)."""
    if pd.isna(valor):
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


# ======================================================================
# Leitura do dicionário de dados
# ======================================================================

def ler_dicionario(dict_path: Path) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """Lê a aba 'DICIONÁRIO' e devolve:
        column_rename: {codigo_variavel: descricao_adaptada}
        value_maps:    {codigo_variavel: {codigo_categoria: descricao_categoria}}
    """
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
        tem_codigo = isinstance(codigo, str) and codigo != ""

        if tem_codigo:
            desc_vazia = not (isinstance(desc, str) and desc.strip())
            cat_codigo_vazio = not (isinstance(cat_codigo, str) and cat_codigo.strip())
            if desc_vazia and cat_codigo_vazio:
                # cabeçalho de seção ou nota de rodapé (ex.: "Variáveis
                # Derivadas") -> não é uma variável de fato, ignora
                codigo_atual = None
                continue

            codigo_atual = codigo
            adaptada = adaptar_descricao_variavel(desc)
            column_rename[codigo_atual] = padronizar_texto(adaptada) if SLUGIFY_COLUMN_NAMES else adaptada
            value_maps.setdefault(codigo_atual, {})

        if codigo_atual is None:
            continue

        cat_codigo_limpo = cat_codigo.strip() if isinstance(cat_codigo, str) else cat_codigo
        if not cat_codigo_limpo or cat_codigo_limpo in NO_CATEGORY_MARKERS:
            continue

        cat_desc_limpa = limpar_texto(cat_desc)
        if SLUGIFY_VALUES:
            cat_desc_limpa = padronizar_texto(cat_desc_limpa)
        value_maps[codigo_atual][cat_codigo_limpo] = cat_desc_limpa

    value_maps = {k: v for k, v in value_maps.items() if v}  # remove variáveis sem categoria
    return column_rename, value_maps


# ======================================================================
# Aplicação do dicionário aos microdados
# ======================================================================

def aplicar_dicionario(df: pd.DataFrame, column_rename: dict, value_maps: dict) -> pd.DataFrame:
    df = df.copy()

    # recodifica valores (código -> descrição) antes de renomear colunas,
    # enquanto ainda temos o código original da variável
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


# ======================================================================
# Processamento
# ======================================================================

def processar_ano(ano: str, csv_path: Path, dict_path: Path, processed_dir: Path) -> Path:
    logger.info(f"[{ano}] Lendo dicionário: {dict_path.name}")
    column_rename, value_maps = ler_dicionario(dict_path)
    logger.info(f"[{ano}] {len(column_rename)} variáveis mapeadas ({len(value_maps)} com categorias a recodificar).")

    logger.info(f"[{ano}] Lendo CSV bruto: {csv_path.name}")
    raw_df = pd.read_csv(csv_path, sep=CSV_SEP, encoding=CSV_ENCODING, dtype=str)
    logger.info(f"[{ano}] CSV bruto: {raw_df.shape[0]} linhas x {raw_df.shape[1]} colunas.")

    faltantes = set(raw_df.columns) - set(column_rename.keys())
    if faltantes:
        logger.warning(f"[{ano}] {len(faltantes)} coluna(s) do CSV não constam no dicionário e serão mantidas como estão: {sorted(faltantes)}")

    tratado_df = aplicar_dicionario(raw_df, column_rename, value_maps)

    processed_dir.mkdir(parents=True, exist_ok=True)
    output_path = processed_dir / OUTPUT_FILENAME_TEMPLATE.format(year=ano)
    tratado_df.to_csv(output_path, sep=CSV_SEP, index=False, encoding=CSV_ENCODING)
    logger.info(f"[{ano}] ✓ Arquivo tratado salvo em: {output_path}")
    return output_path


# ======================================================================
# Orquestração
# ======================================================================

def processar_datasen_vd(
    landing_dir: Path = LANDING_DIR,
    dict_dir: Path = DICT_DIR,
    processed_dir: Path = PROCESSED_DIR,
) -> None:
    logger.info(f"Pasta de CSVs:        {landing_dir}")
    logger.info(f"Pasta de dicionários: {dict_dir}")

    # ---------------------------------------------------------
    # FASE 1: Descobrir pares CSV/dicionário casados por ano
    # ---------------------------------------------------------
    pares = descobrir_pares_por_ano(landing_dir, dict_dir)
    if not pares:
        logger.error(
            f"Nenhum par CSV/dicionário casado por ano foi encontrado "
            f"(padrões: '{CSV_GLOB_PATTERN}' em '{landing_dir}', '{DICT_GLOB_PATTERN}' em '{dict_dir}')."
        )
        return

    logger.info(f"{len(pares)} ano(s) encontrado(s) com CSV + dicionário: {sorted(pares)}")

    # ---------------------------------------------------------
    # FASE 2: Processar cada ano
    # ---------------------------------------------------------
    sucesso, falha = [], []
    for idx, (ano, (csv_path, dict_path)) in enumerate(pares.items(), 1):
        logger.info(f"[{idx}/{len(pares)}] Processando ano {ano}...")
        try:
            processar_ano(ano, csv_path, dict_path, processed_dir)
            sucesso.append(ano)
        except Exception as e:
            logger.error(f"❌ Falha ao processar o ano {ano}: {e}")
            falha.append(ano)

    logger.info(f"Concluído. Sucesso: {sucesso}. Falhas: {falha or 'nenhuma'}.")


if __name__ == "__main__":
    processar_datasen_vd()