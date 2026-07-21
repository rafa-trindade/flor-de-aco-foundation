"""Processamento Datajud (CNJ) -> Parquet por recorte.

Atenção à GRANULARIDADE: Uma linha por `ID_DATAJUD`, não por processo. 
`NUMERO_PROCESSO` se repete em instâncias/órgãos diferentes. Use COUNT(DISTINCT).
Nota de negócio: Base contém apenas metadados processuais (sem dados das partes/vítimas).

Uso:
    python -m scripts.process.datajud.process_datajud_violencia [recorte]
"""
import sys
import logging

from scripts.common.paths import MANUAL_DIR
from scripts.common.publish import query_para_parquet
from scripts.common import exit_codes
from scripts.config.datajud_tpu import (
    RECORTES, NOMES, CONTEXTO_DOMESTICO, FEMINICIDIO, MEDIDA_PROTETIVA,
    QUALIFICADORES, VIOLENCIA_TIPIFICADA, INDICIO_CONSUMACAO,
    PRIORIDADE_LEITURA, CLASSES_MEDIDA_PROTETIVA,
)

logger = logging.getLogger(__name__)

ENTRADA_DIR = MANUAL_DIR / "datajud"
PASTA_BUCKET = "datajud"

# Filtro de sanidade: Acervo anterior a 1990 indica corrupção de dado na origem.
ANO_MINIMO = 1990

# Mitigação de anomalia: Processos com dezenas de assuntos são dumps acidentais 
# da tabela de domínio da TPU pelo Tribunal.
LIMITE_ASSUNTOS_PLAUSIVEL = 20

# Preenchimento determinístico de UF via sigla do Tribunal (cobre lacuna de ~11% 
# sem codigoMunicipioIBGE).
UF_POR_TRIBUNAL = {
    "TJAC": "AC", "TJAL": "AL", "TJAM": "AM", "TJAP": "AP", "TJBA": "BA",
    "TJCE": "CE", "TJDFT": "DF", "TJES": "ES", "TJGO": "GO", "TJMA": "MA",
    "TJMG": "MG", "TJMS": "MS", "TJMT": "MT", "TJPA": "PA", "TJPB": "PB",
    "TJPE": "PE", "TJPI": "PI", "TJPR": "PR", "TJRJ": "RJ", "TJRN": "RN",
    "TJRO": "RO", "TJRR": "RR", "TJRS": "RS", "TJSC": "SC", "TJSE": "SE",
    "TJSP": "SP", "TJTO": "TO",
}


def _lista_nomes_sql() -> str:
    itens = ", ".join(
        f"{cod}: '{nome.replace(chr(39), chr(39) * 2)}'"
        for cod, nome in sorted(NOMES.items())
    )
    return f"MAP {{{itens}}}"


def _query(recorte: str, ano_max: int) -> str:
    padrao = str(ENTRADA_DIR / recorte / "*.ndjson").replace("\\", "/")

    # Workaround DuckDB: O JSON path recursivo ('$..codigo') contorna 
    # a presença de arrays malformados (array de arrays) na origem, impedindo o aborto da query.
    cods = ("list_transform(json_extract(TRY_CAST(assuntos AS JSON), "
            "'$..codigo'), x -> TRY_CAST(x AS INTEGER))")
    noms = (f"list_transform({cods}, x -> COALESCE(dicionario.m[x], "
            f"'ASSUNTO ' || x))")

    # Extração tipada via JSON impede que `read_ndjson` infira structs com tipos mistos 
    # (ex: int e string no mesmo campo) que corrompem a leitura no Dremio (serializando em Base64).
    def _num(campo: str, chave: str) -> str:
        return (f"TRY_CAST(json_extract_string(TRY_CAST({campo} AS JSON), "
                f"'$.{chave}') AS BIGINT)")

    def _txt(campo: str, chave: str) -> str:
        return (f"json_extract_string(TRY_CAST({campo} AS JSON), '$.{chave}')")

    _map_uf = "MAP {" + ", ".join(
        f"'{t}': '{uf}'" for t, uf in sorted(UF_POR_TRIBUNAL.items())
    ) + "}"

    codigos_contexto = ", ".join(str(c) for c in CONTEXTO_DOMESTICO)
    codigos_femin = ", ".join(str(c) for c in FEMINICIDIO)
    codigos_protetiva = ", ".join(str(c) for c in MEDIDA_PROTETIVA)
    codigos_qualif = ", ".join(str(c) for c in QUALIFICADORES)
    codigos_tipificada = ", ".join(str(c) for c in VIOLENCIA_TIPIFICADA)
    codigos_consumacao = ", ".join(str(c) for c in INDICIO_CONSUMACAO)
    classes_protetiva = ", ".join(str(c) for c in CLASSES_MEDIDA_PROTETIVA)

    # Ordenação semântica forçada (forma > tipo > qualificadora > contexto).
    prioridade = "MAP {" + ", ".join(
        f"{c}: {p}" for c, p in sorted(PRIORIDADE_LEITURA.items())
    ) + "}"

    # Regex parsing multinível para contornar três padrões simultâneos na API:
    # String 14 chars, ISO-8601, e Epoch MS (int). Trim no varchar neutraliza aspas do JSON.
    bruto = "trim(TRY_CAST(dataAjuizamento AS VARCHAR), '\"')"
    dt_valida = f"""
        CASE
            WHEN regexp_full_match({bruto}, '[0-9]{{14}}')
                THEN TRY_CAST(TRY_STRPTIME({bruto}, '%Y%m%d%H%M%S') AS DATE)
            WHEN regexp_full_match({bruto}, '[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}T.*')
                THEN TRY_CAST(substr({bruto}, 1, 10) AS DATE)
            WHEN regexp_full_match({bruto}, '[0-9]{{10,13}}')
                THEN TRY_CAST(
                    epoch_ms(TRY_CAST({bruto} AS BIGINT)) AS DATE
                )
        END
    """

    dt_valida = f"""
        CASE WHEN year({dt_valida}) BETWEEN {ANO_MINIMO} AND {ano_max}
             THEN {dt_valida} END
    """

    # Fallback de ano: Extração posicional do ano (10-13) conforme Res. 65/2008 
    # do CNJ (NNNNNNNDD AAAA J TR OOOO).
    ano_numero = f"""
        CASE WHEN regexp_full_match(numeroProcesso, '[0-9]{{20}}')
             THEN TRY_CAST(substr(numeroProcesso, 10, 4) AS INTEGER)
        END
    """

    return f"""
        WITH bruto AS (
            SELECT * FROM read_ndjson('{padrao}', union_by_name=true)
        ),
        deduplicado AS (
            -- Deduplica exclusivamente versões do mesmo documento (campo `id` do Datajud),
            -- mantendo a multiplicidade legítima de um processo em órgãos/classes distintos.
            SELECT * FROM bruto
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY id
                ORDER BY dataHoraUltimaAtualizacao DESC
            ) = 1
        ),
        -- Dicionário de fallback: Reconstrói o mapeamento cód->nome a partir de 
        -- registros íntegros para contornar arrays dessincronizados/malformados na origem.
        pares AS (
            SELECT DISTINCT
                TRY_CAST(unnest(json_extract(
                    TRY_CAST(assuntos AS JSON), '$..codigo')) AS INTEGER) AS cod,
                trim(TRY_CAST(unnest(json_extract(
                    TRY_CAST(assuntos AS JSON), '$..nome')) AS VARCHAR), '"') AS nome
            FROM deduplicado
            WHERE len(json_extract(TRY_CAST(assuntos AS JSON), '$..codigo'))
                = len(json_extract(TRY_CAST(assuntos AS JSON), '$..nome'))
        ),
        dicionario AS (
            SELECT map(list(cod), list(nome)) AS m FROM (
                SELECT cod, min(nome) AS nome FROM pares
                WHERE cod IS NOT NULL GROUP BY cod
            )
        )
        SELECT
            TRY_CAST(id AS VARCHAR)                     AS ID_DATAJUD,
            TRY_CAST(numeroProcesso AS VARCHAR)         AS NUMERO_PROCESSO,
            TRY_CAST(tribunal AS VARCHAR)               AS TRIBUNAL,
            {_map_uf}[TRY_CAST(tribunal AS VARCHAR)]    AS UF,
            TRY_CAST(grau AS VARCHAR)                   AS GRAU,

            {dt_valida}                                 AS DT_AJUIZAMENTO,
            {bruto}                                     AS DT_AJUIZAMENTO_ORIGEM,
            COALESCE(
                year({dt_valida}),
                CASE WHEN {ano_numero} BETWEEN {ANO_MINIMO} AND {ano_max}
                     THEN {ano_numero} END
            )                                           AS ANO_AJUIZAMENTO,
            -- Flag de confiabilidade temporal (Data da Capa vs Parser Numérico).
            CASE WHEN {dt_valida} IS NOT NULL THEN 'DATA'
                 WHEN {ano_numero} BETWEEN {ANO_MINIMO} AND {ano_max}
                      THEN 'NUMERO_PROCESSO'
            END                                         AS ORIGEM_ANO_AJUIZAMENTO,

            {_num('classe','codigo')}                   AS COD_CLASSE,
            {_txt('classe','nome')}                     AS CLASSE,

            len({cods})                                 AS QTD_ASSUNTOS,
            len({cods}) > {LIMITE_ASSUNTOS_PLAUSIVEL}   AS ASSUNTOS_IMPLAUSIVEL,
            -- Casting para string agregada. Evita estouro de array (Dremio limit: 128 itens) e dispensa FLATTEN a jusante.
            list_aggregate(
                list_transform(
                    list_sort(list_distinct(list_transform(
                        {cods},
                        x -> [COALESCE({prioridade}[x], 99),
                              COALESCE(list_position({cods}, x), 0)]
                    ))),
                    par -> {noms}[par[2]]
                ), 'string_agg', ', ')                  AS ASSUNTOS,
            list_aggregate(list_sort(list_distinct({cods})),
                           'string_agg', ', ')          AS COD_ASSUNTOS,


            list_has_any({cods}, [{codigos_femin}])     AS TEM_FEMINICIDIO,
            -- Distinção de instâncias: DESCUMPRIMENTO é Assunto (infração penal); EH_MEDIDA_PROTETIVA é Classe processual (o pedido em si).
            list_has_any({cods}, [{codigos_protetiva}]) AS TEM_DESCUMPRIMENTO_PROTETIVA,
            {_num('classe','codigo')} IN ({classes_protetiva})
                                                        AS EH_MEDIDA_PROTETIVA,
            list_has_any({cods}, [{codigos_contexto}])  AS TEM_CONTEXTO_DOMESTICO,
            list_has_any({cods}, [{codigos_tipificada}]) AS TEM_VIOLENCIA_TIPIFICADA,
            list_has_any({cods}, [{codigos_qualif}])    AS TEM_CRIME_TENTADO,

            -- Inferência de desfecho: CONSUMADO usa proxies estritos (ex: ocultação de cadáver).
            -- A ausência da flag 'Tentativa' resulta em NULL e não em 'Consumado' (alta subnotificação nos TJs).
            CASE
                WHEN list_has_any({cods}, [{codigos_qualif}]) THEN 'TENTATIVA'
                WHEN list_has_any({cods}, [{codigos_consumacao}]) THEN 'CONSUMADO'
            END                                         AS DESFECHO,

            {_num('orgaoJulgador','codigo')}            AS COD_ORGAO_JULGADOR,
            {_txt('orgaoJulgador','nome')}              AS ORGAO_JULGADOR,
            {_num('orgaoJulgador','codigoMunicipioIBGE')} AS COD_MUNICIPIO_IBGE,

            {_txt('formato','nome')}                    AS FORMATO,
            TRY_CAST(nivelSigilo AS INTEGER)            AS NIVEL_SIGILO,
            TRY_CAST(dataHoraUltimaAtualizacao AS TIMESTAMP) AS DT_ULTIMA_ATUALIZACAO
        FROM deduplicado, dicionario
    """


def main(argv: list[str]) -> int:
    from datetime import datetime

    recorte = argv[0] if argv else "feminicidio"
    if recorte not in RECORTES:
        logger.error(f"Recorte '{recorte}' inválido. Use: {', '.join(RECORTES)}")
        return exit_codes.ERRO

    origem = ENTRADA_DIR / recorte
    if not origem.exists() or not any(origem.glob("*.ndjson")):
        logger.error(
            f"Nenhum NDJSON em {origem} -- rode o extract antes:\n"
            f"  python -m scripts.extract.datajud.fetch_datajud_violencia {recorte}"
        )
        return exit_codes.ERRO

    arquivos = sorted(origem.glob("*.ndjson"))
    logger.info(f"{len(arquivos)} tribunal(is) em {origem}.")

    ano_max = datetime.now().year

    ok = query_para_parquet(
        _query(recorte, ano_max), PASTA_BUCKET, f"datajud_{recorte}.parquet"
    )
    return exit_codes.SUCESSO if ok else exit_codes.ERRO


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))