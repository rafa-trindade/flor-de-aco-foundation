"""Processamento SINAN/DATASUS: Notificações de violência interpessoal contra mulheres.

Regras de negócio:
- Recorte restrito a vítimas femininas (CS_SEXO='F').
- Exclui autoextermínio/lesão autoprovocada (LES_AUTOP=1).
- Sem limite de idade (inclui crianças).
- Contém relação vítima-agressor e casos não fatais (complementando o SIM).
"""
import sys

from scripts.common.paths import LANDING_DIR
from scripts.process.datasus.base_process_dbc import processar_fonte_ftp_incremental
from scripts.config import sinan_viol_dominios as dom

DBC_DIR = LANDING_DIR / "datasus" / "dbc_sinan_violencia"
PASTA_BUCKET = "datasus_sinan"
NOME_ARQUIVO_FINAL = "sinan_violencia_mulher.parquet"


def _map_sql(mapa: dict) -> str:
    itens = ", ".join(f"'{k}': '{v.replace(chr(39), chr(39) * 2)}'" for k, v in mapa.items())
    return f"MAP {{{itens}}}"


def _lookup(mapa: dict, coluna: str) -> str:
    """Injeção SQL para lookup de domínio (com fallback implícito para NULL em chaves inexistentes)."""
    return f"{_map_sql(mapa)}[{coluna}]"


def _lista_marcados(mapa: dict) -> str:
    """Agregação de campos multimarcação (múltiplos 'Sim' por notificação).
    - list_filter: descarta colunas ausentes em layouts pré-2015.
    - list_distinct: resolve duplicação de rótulos por divergência DBF vs PDF (ex: REDE_SAU/ENC_SAUDE).
    - list_sort: garante estabilidade na ordem da lista entre execuções.
    """
    itens = ", ".join(
        f"CASE WHEN {coluna} = '1' THEN '{rotulo}' END"
        for coluna, rotulo in mapa.items()
    )
    return f"list_sort(list_distinct(list_filter([{itens}], x -> x IS NOT NULL)))"


def _tem_algum(colunas: list[str]) -> str:
    return " OR ".join(f"{c} = '1'" for c in colunas)


# Fix de schema: O layout pré-SINAN NET 5.0 (2015) omite diversas colunas.
# Injetar colunas faltantes evita BinderException no DuckDB caso um lote inteiro use o layout antigo.
_COLUNAS_ESPERADAS = [
    "DT_NOTIFIC", "NU_ANO", "DT_OCOR", "HORA_OCOR", "SG_UF_NOT", "ID_MUNICIP",
    "TP_UNI_EXT", "NU_IDADE_N", "ANO_NASC", "CS_SEXO", "CS_RACA", "CS_ESCOL_N", "CS_GESTANT",
    "SIT_CONJUG", "ORIENT_SEX", "IDENT_GEN", "SG_UF", "ID_MN_RESI", "ZONA",
    "SG_UF_OCOR", "ID_MN_OCOR", "ZONA_OCOR", "LOCAL_OCOR", "OUT_VEZES",
    "LES_AUTOP", "NDUPLIC", "NDUPLIC_N", "VIOL_MOTIV", "NUM_ENVOLV", "AUTOR_SEXO", "CICL_VID_AUTOR",
    "AUTOR_ALCO", "REL_TRAB", "CIRC_LESAO", "DT_ENCERRA", "CICL_VID",
] + list(dom.VINCULO_AGRESSOR) + list(dom.TIPO_VIOLENCIA) + list(dom.MEIO_AGRESSAO) \
  + list(dom.TIPO_VIOLENCIA_SEXUAL) + list(dom.DEFICIENCIA) + list(dom.ENCAMINHAMENTO)


def filtro_violencia_mulher(df):
    """Otimização de memória e filtro de negócio (aplicado por chunk).
    - Mantém LES_AUTOP nulo/ignorado (campo apenas essencial, não obrigatório).
    - Descarta NDUPLIC=2 (duplicidade confirmada pelo SINAN).
    """
    if "CS_SEXO" not in df.columns:
        return df.iloc[0:0]

    recorte = df[df["CS_SEXO"] == "F"]
    if "LES_AUTOP" in recorte.columns:
        recorte = recorte[recorte["LES_AUTOP"] != "1"]
    for col_dup in ("NDUPLIC", "NDUPLIC_N"):
        if col_dup in recorte.columns:
            recorte = recorte[recorte[col_dup] != "2"]
    if recorte.empty:
        return recorte

    faltando = [c for c in _COLUNAS_ESPERADAS if c not in recorte.columns]
    if faltando:
        recorte = recorte.assign(**{c: None for c in faltando})
    return recorte


def _query_transformacao() -> str:
    # Parser do campo composto NU_IDADE_N (Dígito 1: unidade cronológica; Dígitos 2-4: valor).
    # A validação regex estrita impede corrupção silenciosa de idades por substr em strings malformadas.
    valido = "regexp_matches(NU_IDADE_N, '^[1-4][0-9]{3}$')"
    unidade = "substr(NU_IDADE_N, 1, 1)"
    valor = "TRY_CAST(substr(NU_IDADE_N, 2, 3) AS INTEGER)"
    # Idades > 120 anos são tipografia incorreta (outliers reais, não valores sentinela).
    # Convertidos para NULL para preservar a notificação sem distorcer médias.
    idade_anos = f"""
        CASE
            WHEN NOT {valido} THEN NULL
            WHEN {unidade} = '4' AND {valor} <= 120 THEN {valor}
            WHEN {unidade} IN ('1', '2', '3') THEN 0
        END
    """

    vinculos = _lista_marcados(dom.VINCULO_AGRESSOR)
    intimo = _tem_algum(dom.VINCULOS_PARCEIRO_INTIMO)
    familiar = _tem_algum(dom.VINCULOS_FAMILIARES)

    # Classificação de Violência de Gênero (Três estados, não booleano).
    # Mantém casos de violência infantil geral.
    # Quando todos os indícios são nulos, classifica como NULL ("indeterminado") e não FALSE.
    sexual = "VIOL_SEXU = '1'"
    sexismo = "VIOL_MOTIV IN ('1', '01')"
    # Campos que sustentam a classificação. Se todos forem NULL ou
    # ignorado, não há base para afirmar nem negar.
    classificavel = " OR ".join(
        f"{c} IN ('1', '2')" for c in
        ["VIOL_SEXU"] + dom.VINCULOS_PARCEIRO_INTIMO
    )
    indicio_genero = f"""
        CASE
            WHEN {sexual} OR {sexismo} OR ({intimo}) THEN 'SIM'
            WHEN {classificavel} THEN 'NAO'
        END
    """


    # Parsing defensivo de datas: COALESCE suporta tanto YYYYMMDD 
    # (padrão DBF) quanto strings com separadores.
    def _data(coluna: str) -> str:
        return (
            f"COALESCE("
            f"TRY_CAST(TRY_STRPTIME({coluna}, '%Y%m%d') AS DATE), "
            f"TRY_CAST({coluna} AS DATE))"
        )

    dt_notif = _data("DT_NOTIFIC")
    dt_ocor = _data("DT_OCOR")

    # Prevenção de vazamento PII (LGPD): Proíbe SELECT *. 
    # Garante que identificadores (Nome, CNS, Endereço) não vazem se 
    # o DATASUS alterar o layout público no futuro.
    return f"""
        SELECT * EXCLUDE (VINCULOS_TMP),
            VINCULOS_TMP                                        AS VINCULOS_AGRESSOR,
            len(VINCULOS_TMP)                                   AS QTD_VINCULOS_AGRESSOR
        FROM (
        SELECT
            {dt_notif}                                          AS DT_NOTIFICACAO,
            TRY_CAST(NU_ANO AS INTEGER)                         AS ANO_NOTIFICACAO,
            {dt_ocor}                                           AS DT_OCORRENCIA,
            HORA_OCOR                                           AS HORA_OCORRENCIA,
            -- Flag de consistência temporal. Violações de DT_OCOR <= DT_NOTIFIC ocorrem no DBF, marcamos em vez de descartar o registro.
            CASE
                WHEN {dt_ocor} IS NULL OR {dt_notif} IS NULL THEN NULL
                ELSE {dt_ocor} <= {dt_notif}
            END                                                 AS DATAS_CONSISTENTES,
            SG_UF_NOT                                           AS UF_NOTIFICACAO,
            ID_MUNICIP                                          AS COD_MUNICIPIO_NOTIFIC,
            {_lookup(dom.UNIDADE_NOTIFICADORA, 'TP_UNI_EXT')}   AS UNIDADE_NOTIFICADORA,

            {idade_anos}                                        AS IDADE_ANOS,
            NU_IDADE_N                                          AS IDADE_CODIGO_ORIGEM,
            COALESCE(NDUPLIC, NDUPLIC_N)                        AS MARCA_DUPLICIDADE_ORIGEM,
            TRY_CAST(ANO_NASC AS INTEGER)                       AS ANO_NASCIMENTO,
            {_lookup(dom.SEXO, 'CS_SEXO')}                      AS SEXO,
            {_lookup(dom.RACA_COR, 'CS_RACA')}                  AS RACA_COR,
            {_lookup(dom.ESCOLARIDADE, 'CS_ESCOL_N')}           AS ESCOLARIDADE,
            {_lookup(dom.GESTANTE, 'CS_GESTANT')}               AS GESTANTE,
            {_lookup(dom.SITUACAO_CONJUGAL, 'SIT_CONJUG')}      AS SITUACAO_CONJUGAL,
            {_lookup(dom.ORIENTACAO_SEXUAL, 'ORIENT_SEX')}      AS ORIENTACAO_SEXUAL,
            {_lookup(dom.IDENTIDADE_GENERO, 'IDENT_GEN')}       AS IDENTIDADE_GENERO,

            SG_UF                                               AS UF_RESIDENCIA,
            ID_MN_RESI                                          AS COD_MUNICIPIO_RESID,
            {_lookup(dom.ZONA, 'ZONA')}                         AS ZONA_RESIDENCIA,

            SG_UF_OCOR                                          AS UF_OCORRENCIA,
            ID_MN_OCOR                                          AS COD_MUNICIPIO_OCOR,
            {_lookup(dom.ZONA, 'ZONA_OCOR')}                    AS ZONA_OCORRENCIA,
            {_lookup(dom.LOCAL_OCORRENCIA, 'LOCAL_OCOR')}       AS LOCAL_OCORRENCIA,

            {_lookup(dom.SIM_NAO, 'OUT_VEZES')}                 AS VIOLENCIA_DE_REPETICAO,
            {_lookup(dom.SIM_NAO_NA, 'LES_AUTOP')}              AS LESAO_AUTOPROVOCADA,
            {_lookup(dom.VIOLENCIA_MOTIVADA, 'VIOL_MOTIV')}     AS VIOLENCIA_MOTIVADA_POR,

            {_lista_marcados(dom.TIPO_VIOLENCIA)}               AS TIPOS_VIOLENCIA,
            {_lista_marcados(dom.MEIO_AGRESSAO)}                AS MEIOS_AGRESSAO,
            {_lista_marcados(dom.TIPO_VIOLENCIA_SEXUAL)}        AS TIPOS_VIOLENCIA_SEXUAL,
            {_lista_marcados(dom.DEFICIENCIA)}                  AS DEFICIENCIAS,
            {_lista_marcados(dom.ENCAMINHAMENTO)}               AS ENCAMINHAMENTOS,

            {vinculos}                                          AS VINCULOS_TMP,
            COALESCE({intimo}, FALSE)                           AS AGRESSOR_PARCEIRO_INTIMO,
            COALESCE({familiar}, FALSE)                         AS AGRESSOR_FAMILIAR,
            {indicio_genero}                                    AS INDICIO_VIOLENCIA_GENERO,

            {_lookup(dom.NUMERO_ENVOLVIDOS, 'NUM_ENVOLV')}      AS NUMERO_ENVOLVIDOS,
            {_lookup(dom.SEXO_AGRESSOR, 'AUTOR_SEXO')}          AS SEXO_AGRESSOR,
            {_lookup(dom.CICLO_VIDA_AGRESSOR, 'COALESCE(CICL_VID, CICL_VID_AUTOR)')} AS CICLO_VIDA_AGRESSOR,
            {_lookup(dom.SIM_NAO, 'AUTOR_ALCO')}                AS AGRESSOR_SUSPEITA_ALCOOL,

            {_lookup(dom.SIM_NAO, 'REL_TRAB')}                  AS VIOLENCIA_RELACIONADA_TRABALHO,
            CIRC_LESAO                                          AS CID_CIRCUNSTANCIA_LESAO,
            {_data('DT_ENCERRA')}                               AS DT_ENCERRAMENTO,
            _ARQUIVO_ORIGEM
        FROM __ORIGEM__
        )
    """


if __name__ == "__main__":
    sys.exit(processar_fonte_ftp_incremental(
        dbc_dir=DBC_DIR,
        pasta_bucket=PASTA_BUCKET,
        nome_arquivo_final=NOME_ARQUIVO_FINAL,
        filtro_chunk=filtro_violencia_mulher,
        query_transformacao=_query_transformacao(),
    ))