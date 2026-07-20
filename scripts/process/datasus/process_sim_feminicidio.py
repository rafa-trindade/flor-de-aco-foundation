"""SIM/DATASUS -- óbitos femininos por agressão (CID-10 X85-Y09).

Recorte: SEXO = 2 (feminino) e CAUSABAS no grupo de agressões. O filtro
roda já na Fase 1 (por chunk), antes de escrever os parquets
intermediários -- a maior parte do arquivo de causas externas é
irrelevante aqui e não vale carregar adiante.

Y35 (intervenção legal) NÃO entra: a CID-10 o exclui do grupo de
agressões. Ver scripts/config/cid_agressao.py.
"""
import sys

from scripts.common.paths import LANDING_DIR
from scripts.process.datasus.base_process_dbc import processar_fonte_ftp_incremental
from scripts.config.cid_agressao import (
    CID_METODO, CID_LOCAL, CID_AGRESSOR,
    CATEGORIAS_SUBDIVIDIDAS_POR_AGRESSOR, CODIGOS_AGRESSAO,
)
from scripts.config import sim_dominios

DBC_DIR = LANDING_DIR / "datasus" / "dbc_sim_causas_externas"
PASTA_BUCKET = "datasus_sim"
NOME_ARQUIVO_FINAL = "feminicidio_serie_historica.parquet"


def _map_sql(mapa: dict) -> str:
    """Literal MAP do DuckDB a partir de um dict."""
    itens = ", ".join(f"'{k}': '{v.replace(chr(39), chr(39)*2)}'" for k, v in mapa.items())
    return f"MAP {{{itens}}}"


def _lookup(mapa: dict, coluna: str) -> str:
    """Lookup com fallback NULL quando a chave não existe no domínio."""
    return f"{_map_sql(mapa)}[{coluna}]"


def filtro_feminicidio(df):
    """Só óbitos femininos por agressão. Aplicado por chunk na Fase 1."""
    if "SEXO" not in df.columns or "CAUSABAS" not in df.columns:
        return df.iloc[0:0]
    return df[(df["SEXO"] == "2") & (df["CAUSABAS"].isin(CODIGOS_AGRESSAO))]


def _query_transformacao() -> str:
    categoria = "substr(CAUSABAS, 1, 3)"
    sufixo = "substr(CAUSABAS, 4, 1)"
    por_agressor = ", ".join(f"'{c}'" for c in sorted(CATEGORIAS_SUBDIVIDIDAS_POR_AGRESSOR))

    return f"""
        SELECT
            DTNASC                                  AS DT_NASCIMENTO,
            DTOBITO                                 AS DT_OBITO,
            DTCADASTRO                              AS DT_CADASTRO_OBITO,
            HORAOBITO                               AS HORA_OBITO,
            {_lookup(sim_dominios.SEXO, 'SEXO')}                       AS SEXO,
            {_lookup(sim_dominios.RACA_COR, 'RACACOR')}                AS RACA_COR,
            {_lookup(sim_dominios.ESTADO_CIVIL, 'ESTCIV')}             AS EST_CIVIL,
            CODMUNRES                               AS COD_MUNICIPIO_RESID,
            CODMUNOCOR                              AS COD_MUNICIPIO_OBITO,
            {_lookup(sim_dominios.LOCAL_OCORRENCIA, 'LOCOCOR')}        AS LOCAL_OCORRENCIA_OBITO,
            CAUSABAS                                AS CAUSA_BASICA,
            {_lookup(CID_METODO, categoria)}        AS METODO_AGRESSAO,
            CASE WHEN {categoria} IN ({por_agressor})
                 THEN NULL
                 ELSE {_lookup(CID_LOCAL, sufixo)}
            END                                     AS LOCAL_CID,
            CASE WHEN {categoria} IN ({por_agressor})
                 THEN {_lookup(CID_AGRESSOR, sufixo)}
                 ELSE NULL
            END                                     AS AGRESSOR_CID,
            {_lookup(sim_dominios.CIRCUNSTANCIA_OBITO, 'CIRCOBITO')}   AS TIPO_OBITO,
            {_lookup(sim_dominios.OBITO_GRAVIDEZ, 'OBITOGRAV')}        AS GESTANTE,
            {_lookup(sim_dominios.OBITO_PUERPERIO, 'OBITOPUERP')}      AS PUERPERIO,
            _ARQUIVO_ORIGEM
        FROM __ORIGEM__
    """


if __name__ == "__main__":
    sys.exit(processar_fonte_ftp_incremental(
        dbc_dir=DBC_DIR,
        pasta_bucket=PASTA_BUCKET,
        nome_arquivo_final=NOME_ARQUIVO_FINAL,
        filtro_chunk=filtro_feminicidio,
        query_transformacao=_query_transformacao(),
    ))