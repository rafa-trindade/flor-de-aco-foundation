"""Macrorregião de Saúde + geolocalização dos municípios.

Zero à esquerda é corrigido nos dois lados antes do join: sem isso os
municípios com código iniciado em zero perdem o cruzamento em silêncio.
"""
import sys

import pandas as pd

from scripts.common.paths import LANDING_DIR, MANUAL_MACROREGIAO_DIR
from scripts.common import exit_codes
from scripts.common.publish import query_para_parquet, conectar_duckdb

PASTA_BUCKET = "macroregiao"
NOME_ARQUIVO_FINAL = "geo_macroregiao.parquet"

CSV_LANDING = LANDING_DIR / "macroregiao" / "macroregiao.csv"
XLS_GEO = MANUAL_MACROREGIAO_DIR / "macro_geolocalizacao.xls"


def main() -> int:
    if not CSV_LANDING.exists():
        print(f"[INFO] {CSV_LANDING.name} não está na landing -- nada a processar.")
        return exit_codes.SEM_NOVIDADE

    if not XLS_GEO.exists():
        print(f"[ERRO] '{XLS_GEO.name}' não encontrado. Coloque em {MANUAL_MACROREGIAO_DIR}.")
        return exit_codes.ERRO

    print("Lendo CSV e XLS para ajuste de zeros à esquerda...")
    df = pd.read_csv(CSV_LANDING, sep=";", encoding="utf-8-sig", dtype=str)
    df_geo = pd.read_excel(XLS_GEO, dtype=str)

    df["cod_municipio"] = df["cod_municipio"].str.zfill(6)
    df_geo["MUNCOD"] = df_geo["MUNCOD"].str.zfill(6)

    con = conectar_duckdb()
    con.register("macro", df)
    con.register("geo", df_geo)

    # EXCLUDE (MUNCOD): é a mesma coluna de cod_municipio, e sem isso o
    # resultado sai com a chave de join duplicada.
    query = """
        SELECT m.*, g.* EXCLUDE (MUNCOD)
        FROM macro m
        LEFT JOIN geo g ON m.cod_municipio = g.MUNCOD
    """

    try:
        sucesso = query_para_parquet(query, PASTA_BUCKET, NOME_ARQUIVO_FINAL, con=con)
    finally:
        con.close()

    if not sucesso:
        return exit_codes.ERRO

    CSV_LANDING.unlink(missing_ok=True)
    return exit_codes.SUCESSO


if __name__ == "__main__":
    sys.exit(main())