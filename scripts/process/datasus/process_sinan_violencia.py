"""SINAN/DATASUS -- notificações de violência interpessoal contra mulheres.

Recorte: CS_SEXO='F' e lesão não autoprovocada, filtrado já na Fase 1.

A ficha é "Violência Interpessoal/Autoprovocada" -- LES_AUTOP=1 marca
tentativa de autoextermínio, outro fenômeno. Fica de fora.

Sem recorte de idade: notificações de meninas entram na base, com o
vínculo do agressor distinguindo violência intrafamiliar de parceiro.

Complementa o SIM: registra violência NÃO fatal e traz a relação
vítima-agressor, que a Declaração de Óbito não tem.
"""
import sys

from scripts.common.paths import LANDING_DIR
from scripts.process.datasus.base_process_dbc import processar_fonte_ftp_incremental
from scripts.config import sinan_viol_dominios as dom

DBC_DIR = LANDING_DIR / "datasus" / "dbc_sinan_violencia"
PASTA_BUCKET = "datasus_sinan"
NOME_ARQUIVO_FINAL = "sinan_violencia_mulher.parquet"


def _map_sql(mapa: dict) -> str:
    """Literal MAP do DuckDB a partir de um dict."""
    itens = ", ".join(f"'{k}': '{v.replace(chr(39), chr(39) * 2)}'" for k, v in mapa.items())
    return f"MAP {{{itens}}}"


def _lookup(mapa: dict, coluna: str) -> str:
    """Lookup com fallback NULL quando a chave não existe no domínio."""
    return f"{_map_sql(mapa)}[{coluna}]"


def _lista_marcados(mapa: dict) -> str:
    """LIST com os rótulos das colunas marcadas como Sim.

    Campos multimarcação (tipo de violência, meio de agressão, vínculo com
    o agressor): a ficha aceita vários "Sim" na mesma notificação. Colapsar
    num valor único perderia combinações e exigiria eleger um "principal"
    que a ficha não define.

    list_filter descarta os NULL das colunas ausentes nos layouts
    anteriores a 2015, completadas por filtro_violencia_mulher.

    list_distinct porque alguns rótulos têm duas grafias de coluna (o DBF
    diverge do PDF em REDE_SAU/ENC_SAUDE e DELEG_IDOS/DELEG_IDOSO); se as
    duas existirem e estiverem marcadas, o rótulo sairia repetido.

    list_sort porque list_distinct não preserva ordem: sem isso a mesma
    notificação pode sair com a lista em ordens diferentes entre rodadas.
    A ficha não define prioridade entre marcações, então a ordem não tem
    significado -- alfabética serve, desde que seja estável.
    """
    itens = ", ".join(
        f"CASE WHEN {coluna} = '1' THEN '{rotulo}' END"
        for coluna, rotulo in mapa.items()
    )
    return f"list_sort(list_distinct(list_filter([{itens}], x -> x IS NOT NULL)))"


def _tem_algum(colunas: list[str]) -> str:
    """TRUE se qualquer uma das colunas está marcada como Sim."""
    return " OR ".join(f"{c} = '1'" for c in colunas)


# Colunas que a query_transformacao referencia. O layout anterior ao SINAN
# NET 5.0 (2015) não tem IDENT_GEN, VIOL_MOTIV nem os DEF_*, e o conjunto
# de REL_* também cresceu. union_by_name só alinha os parquets do lote
# entre si: se nenhum arquivo da rodada tiver a coluna, ela não existe no
# consolidado e a query quebra com BinderException. Daí completar aqui.
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
    """Vítimas do sexo feminino, excluindo lesão autoprovocada e duplicatas.

    LES_AUTOP ausente ou '9' (ignorado) não exclui a linha: o campo é
    apenas essencial, não obrigatório, e descartar o ignorado jogaria fora
    notificação válida de violência interpessoal.

    NDUPLIC=2 é duplicidade confirmada pelo próprio SINAN na rotina de
    duplicidade ("não contar"), e infla qualquer contagem se entrar. O
    valor 1 ("não é duplicidade, não listar") e 0/branco ("não
    identificado") são registros válidos e ficam. O nome da coluna varia
    entre competências (NDUPLIC / NDUPLIC_N).
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
    # NU_IDADE_N é composto: 1o dígito é a unidade (1=hora, 2=dia, 3=mês,
    # 4=ano) e os 3 seguintes o valor. 4018 = 18 anos, 3009 = 9 meses.
    # Sem decompor, qualquer agregação por idade sai absurda.
    #
    # O formato é validado antes de fatiar. substr() cego aceitaria '105'
    # (sem o dígito de unidade) lendo unidade=1 e devolvendo 0 anos -- uma
    # competência inteira viraria idade 0 em silêncio. Também rejeita
    # '41050' e '4105.0', que devolveriam 105.
    valido = "regexp_matches(NU_IDADE_N, '^[1-4][0-9]{3}$')"
    unidade = "substr(NU_IDADE_N, 1, 1)"
    valor = "TRY_CAST(substr(NU_IDADE_N, 2, 3) AS INTEGER)"
    # Idade acima de 120 é digitação errada na notificação, não sentinela:
    # a cauda decai suavemente de 105 (26 casos) a 130 (1), sem pico em
    # nenhum valor. São ~21 registros em 2,8M. A linha fica -- a
    # notificação é válida --, só a idade impossível vira NULL, para não
    # entrar em média nem em faixa etária.
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

    # A base mistura dois fenômenos, porque o recorte de entrada é só o
    # sexo da vítima: violência de gênero (sexual, por parceiro, motivada
    # por sexismo) e violência infantil geral, que atinge meninos e meninas
    # igualmente e entra aqui só porque a vítima é do sexo feminino.
    #
    # A pista de que estão misturados está nos próprios dados: REL_MAE
    # (256.662) quase empata com REL_PAI (214.428). Num recorte de gênero
    # isso seria estranho; com negligência infantil dentro, é esperado --
    # mãe é quem mais figura como responsável nesse tipo de notificação.
    #
    # Classificação, não filtro: a notificação fica na base e quem consome
    # decide. Três estados, não booleano -- registro sem nenhum dos campos
    # preenchidos não é "não é violência de gênero", é "não dá para dizer",
    # e colapsar isso em FALSE afirmaria o que o dado não sustenta.
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


    # As datas do DBF chegam como string YYYYMMDD (o base_process_dbc
    # remove o sufixo .0 que o float do pandas introduzia). O COALESCE
    # cobre competências que gravem com separador, em vez de devolver a
    # base inteira com data nula em silêncio.
    def _data(coluna: str) -> str:
        return (
            f"COALESCE("
            f"TRY_CAST(TRY_STRPTIME({coluna}, '%Y%m%d') AS DATE), "
            f"TRY_CAST({coluna} AS DATE))"
        )

    dt_notif = _data("DT_NOTIFIC")
    dt_ocor = _data("DT_OCOR")

    # SELECT explícito por coluna, nunca *: a ficha tem nome, nome da mãe,
    # CNS, endereço e telefone. Os DBCs públicos do FTP não trazem esses
    # campos, mas uma mudança futura no FTP não pode vazar identificação
    # para dentro do Parquet publicado.
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
            -- O dicionário declara DT_OCOR <= DT_NOTIFIC como regra
            -- obrigatória, mas o DBF tem violações. Marcar em vez de
            -- descartar: a notificação é válida, a data é que não confere.
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