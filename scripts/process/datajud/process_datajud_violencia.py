"""CNJ/Datajud -- processos de violência contra a mulher.

Lê o NDJSON bruto que o extract deixa em MANUAL_DIR e publica um Parquet
por recorte.

São metadados processuais: classe, assunto, órgão julgador, datas. A API
não expõe partes, então não há dado da vítima -- a fonte mede
judicialização e tramitação, complementando o SIM (óbito) e o SINAN
(notificação em saúde).

GRANULARIDADE: uma linha por ID_DATAJUD, não por processo. O mesmo
NUMERO_PROCESSO aparece em várias linhas quando tramita em classes ou
órgãos diferentes (apelação num gabinete, agravo em outro). Para contar
processos distintos, use COUNT(DISTINCT NUMERO_PROCESSO).

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

# Ano mínimo plausível para ajuizamento. Anterior a isso é data corrompida
# -- e há muita: no TJAC, 152 de 245 registros não caem em nenhum ano da
# faixa 2005-2026, com o campo preenchido.
ANO_MINIMO = 1990

# Acima disso, o campo assuntos não traz os assuntos do processo: traz um
# despejo da tabela de domínio. Dois registros do TJAL vêm com 565 e 566
# códigos, cobrindo a faixa 3370-3402 inteira (todos os crimes contra a
# pessoa da TPU). Processo real não tem dezenas de assuntos.
LIMITE_ASSUNTOS_PLAUSIVEL = 20

# UF por tribunal. A sigla do TJ identifica o estado de forma
# determinística, e cobre o recorte geográfico dos 11% de registros sem
# codigoMunicipioIBGE -- omissão concentrada em TJSP, TJMT, TJAL e TJAC.
UF_POR_TRIBUNAL = {
    "TJAC": "AC", "TJAL": "AL", "TJAM": "AM", "TJAP": "AP", "TJBA": "BA",
    "TJCE": "CE", "TJDFT": "DF", "TJES": "ES", "TJGO": "GO", "TJMA": "MA",
    "TJMG": "MG", "TJMS": "MS", "TJMT": "MT", "TJPA": "PA", "TJPB": "PB",
    "TJPE": "PE", "TJPI": "PI", "TJPR": "PR", "TJRJ": "RJ", "TJRN": "RN",
    "TJRO": "RO", "TJRR": "RR", "TJRS": "RS", "TJSC": "SC", "TJSE": "SE",
    "TJSP": "SP", "TJTO": "TO",
}


def _lista_nomes_sql() -> str:
    """MAP código -> nome dos assuntos conhecidos, para rotular."""
    itens = ", ".join(
        f"{cod}: '{nome.replace(chr(39), chr(39) * 2)}'"
        for cod, nome in sorted(NOMES.items())
    )
    return f"MAP {{{itens}}}"


def _query(recorte: str, ano_max: int) -> str:
    padrao = str(ENTRADA_DIR / recorte / "*.ndjson").replace("\\", "/")

    # assuntos vem como array de objetos, mas 4 registros em 36 mil
    # trazem array de ARRAYS (com 38, 317, 417 e 566 itens) -- e
    # list_transform(x -> x.codigo) aborta a query inteira nesses.
    # Extrair via JSON path é indiferente ao aninhamento.
    #
    # Nesses 4 a lista sai vazia em vez de aninhada: perde-se o assunto
    # de 4 registros, contra perder a publicação inteira. Se algum dia
    # importarem, o NDJSON bruto em MANUAL_DIR tem o dado original.
    # '$..codigo' é busca recursiva: casa tanto o array de objetos normal
    # quanto o array de ARRAYS de 98 registros anômalos. Com '$[*]' esses
    # 98 saíam com código e sem nome -- linha incoerente, porque o
    # caminho descia um nível para um e não para o outro.
    #
    # A recursão é segura por ser aplicada só ao campo assuntos: sobre o
    # documento inteiro pegaria também classe.codigo e formato.codigo.
    cods = ("list_transform(json_extract(TRY_CAST(assuntos AS JSON), "
            "'$..codigo'), x -> TRY_CAST(x AS INTEGER))")
    noms = (f"list_transform({cods}, x -> COALESCE(dicionario.m[x], "
            f"'ASSUNTO ' || x))")

    # Campos aninhados extraídos via JSON, não por acesso a struct.
    #
    # Basta UM registro com tipo divergente para o read_ndjson desistir de
    # unificar a coluna e serializá-la como binário -- que o Dremio exibe
    # em Base64 ('Mjgy' é '282'). Aconteceu com classe.codigo, onde 2
    # registros em 40.108 vêm como string '-1' e estragaram a leitura dos
    # outros 40.106. O CAST explícito é imune a isso.
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

    # Ordem de leitura: forma > tipo > qualificadora de gênero > contexto.
    # Alfabética espalha essa hierarquia ao acaso e esconde o que
    # distingue tentativa de consumação numa varredura visual.
    prioridade = "MAP {" + ", ".join(
        f"{c}: {p}" for c, p in sorted(PRIORIDADE_LEITURA.items())
    ) + "}"

    # dataAjuizamento chega em três formatos na mesma coleta, verificados
    # sobre 36.352 registros do recorte de feminicídio:
    #   35.304  '20150729093223'            string AAAAMMDDHHMMSS
    #    1.043  '2016-07-15T11:07:14.000Z'  string ISO-8601
    #        5   1531796400000              epoch em milissegundos (int)
    #
    # Tratar só o primeiro (o formato dominante) descartaria mil datas
    # válidas em silêncio. O CAST para VARCHAR uniformiza o int antes de
    # testar, já que read_ndjson infere a coluna como texto quando os
    # tipos se misturam.
    # O read_ndjson preserva as aspas do JSON quando a coluna tem tipos
    # mistos (string e número no mesmo campo), então '20150729093223'
    # chega como '"20150729093223"' -- 16 caracteres, e qualquer regex de
    # 14 dígitos falha. O trim é o que faz os três formatos casarem.
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
    # A data válida ainda precisa cair num ano plausível: valor futuro ou
    # anterior ao ANO_MINIMO é corrupção, não dado.
    dt_valida = f"""
        CASE WHEN year({dt_valida}) BETWEEN {ANO_MINIMO} AND {ano_max}
             THEN {dt_valida} END
    """

    # O padrão CNJ do número único (Res. 65/2008) põe o ano de ajuizamento
    # nas posições 10-13: NNNNNNNDD AAAA J TR OOOO. Quando a data está
    # corrompida, o número costuma estar íntegro -- é a única via de
    # recuperar o ano desses registros.
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
            -- Deduplicação pelo `id`, que o glossário do Datajud define
            -- como "Chave Tribunal_Classe_Grau_OrgaoJulgador_
            -- NumeroProcesso" -- a unicidade da própria fonte.
            --
            -- Chave por numeroProcesso+tribunal+grau seria errada: o
            -- mesmo processo tem várias entradas legítimas no mesmo grau,
            -- uma por classe/órgão (apelação num gabinete, agravo em
            -- outro). No TJMG isso colapsava 743 movimentações em 402.
            --
            -- O que se quer eliminar aqui é só a repetição do modo
            -- incremental, em que o MESMO documento reaparece revisado.
            SELECT * FROM bruto
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY id
                ORDER BY dataHoraUltimaAtualizacao DESC
            ) = 1
        ),
        -- 140 registros trazem assuntos malformado: array de arrays,
        -- objeto só com código e sem nome, ou os dois misturados na mesma
        -- lista. Nesses, código e nome saem em quantidades diferentes e
        -- parear por posição desalinha -- foi o que gerou linhas com
        -- código preenchido e nome vazio.
        --
        -- A saída é montar o nome pelo código, a partir de um dicionário
        -- derivado dos próprios registros bem formados (onde as duas
        -- listas têm o mesmo tamanho e o pareamento é confiável). Com
        -- dezenas de milhares de registros, todo código relevante aparece
        -- corretamente em algum deles.
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
            -- Distingue o ano confiável do recuperado: quem for agregar
            -- série temporal precisa saber que parte veio do número do
            -- processo porque a data era inválida.
            CASE WHEN {dt_valida} IS NOT NULL THEN 'DATA'
                 WHEN {ano_numero} BETWEEN {ANO_MINIMO} AND {ano_max}
                      THEN 'NUMERO_PROCESSO'
            END                                         AS ORIGEM_ANO_AJUIZAMENTO,

            {_num('classe','codigo')}                   AS COD_CLASSE,
            {_txt('classe','nome')}                     AS CLASSE,

            len({cods})                                 AS QTD_ASSUNTOS,
            len({cods}) > {LIMITE_ASSUNTOS_PLAUSIVEL}   AS ASSUNTOS_IMPLAUSIVEL,
            -- Assuntos como texto, não lista: coluna LIST estoura o
            -- limite de 128 elementos do Dremio (há processo com 566) e
            -- obriga a FLATTEN em qualquer leitura. Ordenado e sem
            -- repetição, para a mesma combinação sair sempre igual.
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

            -- Flags derivadas dos assuntos. O array traz vários códigos
            -- por processo, então elas não são exclusivas entre si.
            list_has_any({cods}, [{codigos_femin}])     AS TEM_FEMINICIDIO,
            -- Duas coisas distintas, e a diferença é analítica:
            -- DESCUMPRIMENTO vem do assunto (houve violação da protetiva);
            -- EH_MEDIDA_PROTETIVA vem da CLASSE (o processo é o pedido de
            -- proteção em si). Contar protetivas concedidas pelo assunto
            -- de descumprimento subestimaria muito.
            list_has_any({cods}, [{codigos_protetiva}]) AS TEM_DESCUMPRIMENTO_PROTETIVA,
            {_num('classe','codigo')} IN ({classes_protetiva})
                                                        AS EH_MEDIDA_PROTETIVA,
            list_has_any({cods}, [{codigos_contexto}])  AS TEM_CONTEXTO_DOMESTICO,
            list_has_any({cods}, [{codigos_tipificada}]) AS TEM_VIOLENCIA_TIPIFICADA,
            list_has_any({cods}, [{codigos_qualif}])    AS TEM_CRIME_TENTADO,

            -- Três estados, não booleano. TENTATIVA vem de marcador
            -- explícito; CONSUMADO só de indício POSITIVO (assunto que
            -- pressupõe a morte). A ausência de "Crime Tentado" NÃO prova
            -- consumação -- o tribunal pode não ter marcado --, então
            -- esses casos ficam NULL, que é a maioria.
            --
            -- Somar os CONSUMADO como "feminicídios consumados no Brasil"
            -- subestima o número; é um piso conhecido, não o total.
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

    # Ano corrente como teto: data de ajuizamento no futuro é corrupção,
    # não dado.
    ano_max = datetime.now().year

    # Uma tabela por base: o bucket é camada de publicação, não modelo
    # relacional. Quem analisa monta o relacionamento que precisar.
    ok = query_para_parquet(
        _query(recorte, ano_max), PASTA_BUCKET, f"datajud_{recorte}.parquet"
    )
    return exit_codes.SUCESSO if ok else exit_codes.ERRO


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))