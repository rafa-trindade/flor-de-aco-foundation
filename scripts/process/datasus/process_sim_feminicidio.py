import os
import logging
import gc
import shutil
from pathlib import Path

import datasus_dbc
from dbfread import DBF
import pandas as pd
import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ------------------- Dicionário de CIDs -------------------
codigos_agressao = {
    "X850": "Homicídio por disparo de arma de fogo",
    "X851": "Homicídio por arma branca",
    "X852": "Homicídio por envenenamento",
    "X853": "Homicídio por enforcamento, estrangulamento ou sufocação",
    "X854": "Homicídio por afogamento ou submersão",
    "X855": "Homicídio por explosivo",
    "X856": "Homicídio por incêndio, fogo ou chamas",
    "X857": "Homicídio por gases ou vapores",
    "X858": "Homicídio por objeto cortante ou perfurante",
    "X859": "Homicídio por outros meios",
    "X860": "Agressão por substâncias corrosivas",
    "X861": "Agressão por pesticidas ou produtos químicos",
    "X862": "Agressão por gás ou vapor tóxico",
    "X863": "Agressão por outro produto químico não especificado",
    "X864": "Agressão por envenenamento por drogas, medicamentos e substâncias biológicas",
    "X865": "Agressão por envenenamento por outras substâncias",
    "X866": "Agressão por envenenamento por substância não especificada",
    "X867": "Agressão por projétil de arma de fogo",
    "X868": "Agressão por espingarda, carabina ou arma de maior calibre",
    "X869": "Agressão por outro tipo de arma de fogo",
    "X870": "Agressão por disparo de arma de fogo de mão",
    "X871": "Agressão por espingarda, carabina ou arma de maior calibre",
    "X872": "Agressão por outro tipo de arma de fogo",
    "X873": "Agressão por explosivo",
    "X874": "Agressão por fumaça, fogo e chamas",
    "X875": "Agressão por objeto cortante",
    "X876": "Agressão por objeto contundente",
    "X877": "Agressão por enforcamento ou estrangulamento",
    "X878": "Agressão por afogamento",
    "X879": "Agressão por outros meios especificados",
    "X880": "Agressão por gases e vapores",
    "X881": "Agressão por vapor de água quente",
    "X882": "Agressão por substância corrosiva",
    "X883": "Agressão por pesticida",
    "X884": "Agressão por outro produto químico",
    "X885": "Agressão por envenenamento por drogas, medicamentos e substâncias biológicas",
    "X886": "Agressão por envenenamento por outras substâncias",
    "X887": "Agressão por envenenamento por substância não especificada",
    "X888": "Agressão por projétil de arma de fogo",
    "X889": "Agressão por espingarda, carabina ou arma de maior calibre",
    "X890": "Agressão por objeto cortante ou perfurante",
    "X891": "Agressão por objeto contundente",
    "X892": "Agressão por estrangulamento ou sufocação",
    "X893": "Agressão por afogamento",
    "X894": "Agressão por fogo ou chamas",
    "X895": "Agressão por explosivo",
    "X896": "Agressão por armas de fogo",
    "X897": "Agressão por outros meios especificados",
    "X898": "Agressão por substâncias químicas, local especificado",
    "X899": "Agressão com mecanismo não especificado",
    "X900": "Agressão por produto químico não especificado",
    "X901": "Agressão por gás ou vapor tóxico",
    "X902": "Agressão por outro produto químico",
    "X903": "Agressão por envenenamento por drogas, medicamentos e substâncias biológicas",
    "X904": "Agressão por envenenamento por outras substâncias",
    "X905": "Agressão por envenenamento por substância não especificada",
    "X906": "Agressão por projétil de arma de fogo",
    "X907": "Disparo por espingarda ou carabina",
    "X908": "Disparo por outra arma de fogo",
    "X909": "Agressão por arma de fogo não especificada",
    "X910": "Agressão por enforcamento, estrangulamento ou sufocação",
    "X911": "Agressão por estrangulamento com corda ou fio",
    "X912": "Agressão por sufocação manual",
    "X913": "Agressão por outro meio de estrangulamento ou sufocação",
    "X914": "Agressão por enforcamento com outro meio",
    "X915": "Agressão por afogamento ou submersão",
    "X916": "Afogamento intencional em líquido",
    "X917": "Afogamento intencional em água",
    "X918": "Afogamento intencional em outro meio",
    "X919": "Afogamento intencional em meio não especificado",
    "X920": "Agressão por afogamento ou submersão",
    "X921": "Afogamento intencional em água",
    "X922": "Afogamento intencional em outro meio",
    "X923": "Afogamento intencional em meio não especificado",
    "X924": "Agressão por projétil de arma de fogo",
    "X925": "Disparo por espingarda ou carabina",
    "X926": "Disparo por outra arma de fogo",
    "X927": "Agressão por arma de fogo não especificada",
    "X928": "Agressão por projétil de arma de fogo",
    "X929": "Disparo por espingarda ou carabina",
    "X930": "Agressão por disparo de arma de fogo de mão",
    "X931": "Disparo de espingarda ou carabina",
    "X932": "Disparo por outra arma de fogo",
    "X933": "Agressão por arma de fogo não especificada",
    "X934": "Agressão por projétil de arma de fogo",
    "X935": "Disparo por espingarda ou carabina",
    "X936": "Agressão por disparo de arma de fogo de mão",
    "X937": "Disparo de espingarda ou carabina",
    "X938": "Disparo por outra arma de fogo",
    "X939": "Agressão por arma de fogo não especificada",
    "X940": "Disparo por outra arma de fogo",
    "X941": "Agressão por explosivo",
    "X942": "Agressão por fogo, chamas ou fumaça",
    "X943": "Agressão por incêndio proposital",
    "X944": "Agressão por fogo, chamas ou fumaça",
    "X945": "Agressão por incêndio proposital",
    "X946": "Agressão por vapor, líquidos quentes ou gases",
    "X947": "Agressão por objetos quentes",
    "X948": "Agressão por outros meios térmicos",
    "X949": "Agressão por outros meios térmicos",
    "X950": "Agressão por outro tipo de arma de fogo",
    "X951": "Agressão por disparo de arma de fogo de mão",
    "X952": "Disparo de espingarda ou carabina",
    "X953": "Disparo por outra arma de fogo",
    "X954": "Agressão por arma de fogo não especificada",
    "X955": "Agressão por projétil de arma de fogo",
    "X956": "Disparo por espingarda ou carabina",
    "X957": "Agressão por disparo de arma de fogo de mão",
    "X958": "Disparo de espingarda ou carabina",
    "X959": "Disparo por outra arma de fogo",
    "X960": "Agressão por explosivo",
    "X961": "Agressão por fogo, chamas ou fumaça",
    "X962": "Agressão por incêndio proposital",
    "X963": "Agressão por fogo, chamas ou fumaça",
    "X964": "Agressão por incêndio proposital",
    "X965": "Agressão por vapor, líquidos quentes ou gases",
    "X966": "Agressão por objetos quentes",
    "X967": "Agressão por outros meios térmicos",
    "X968": "Agressão por outros meios térmicos",
    "X969": "Agressão por explosivo",
    "X970": "Agressão por fogo, chamas ou fumaça",
    "X971": "Agressão por incêndio proposital",
    "X972": "Agressão por fogo, chamas ou fumaça",
    "X973": "Agressão por incêndio proposital",
    "X974": "Agressão por fogo, chamas ou fumaça",
    "X975": "Agressão por fogo, chamas ou fumaça",
    "X976": "Agressão por incêndio proposital",
    "X977": "Agressão por incêndio proposital",
    "X978": "Agressão por incêndio proposital",
    "X979": "Agressão por incêndio proposital",
    "X980": "Agressão por vapor, líquidos quentes ou gases",
    "X981": "Agressão por objetos quentes",
    "X982": "Agressão por outros meios térmicos",
    "X983": "Agressão por outros meios térmicos",
    "X984": "Agressão por projétil de arma de fogo",
    "X985": "Disparo por espingarda ou carabina",
    "X986": "Agressão por disparo de arma de fogo de mão",
    "X987": "Disparo de espingarda ou carabina",
    "X988": "Disparo por outra arma de fogo",
    "X989": "Agressão por arma de fogo não especificada",
    "X990": "Agressão por objeto cortante ou perfurante",
    "X991": "Agressão por objeto contundente",
    "X992": "Agressão por estrangulamento ou sufocação",
    "X993": "Agressão por afogamento",
    "X994": "Agressão por fogo ou chamas",
    "X995": "Agressão por explosivo",
    "X996": "Agressão por outros meios especificados",
    "X997": "Agressão por outros meios físicos",
    "X998": "Agressão por outros meios químicos",
    "X999": "Agressão por meios não especificados",
    "Y000": "Agressão por arma de fogo não especificada",
    "Y001": "Agressão por objeto cortante",
    "Y002": "Agressão por objeto contundente",
    "Y003": "Agressão por afogamento",
    "Y004": "Agressão por envenenamento",
    "Y005": "Agressão sexual por força física",
    "Y006": "Negligência e abandono pelo cônjuge",
    "Y007": "Negligência e abandono pelos pais",
    "Y008": "Negligência e abandono por conhecido ou amigo",
    "Y009": "Negligência e abandono por pessoa não especificada",
    "Y010": "Agressão por projeção de lugar elevado",
    "Y011": "Agressão por queda de objeto em movimento",
    "Y012": "Agressão por explosão de gás ou vapor",
    "Y013": "Agressão por explosão de outro objeto",
    "Y014": "Agressão por impacto de veículo ferroviário",
    "Y015": "Agressão por impacto de veículo não motorizado",
    "Y016": "Agressão por impacto de objeto em movimento",
    "Y017": "Agressão por impacto de objeto fixo",
    "Y018": "Agressão por impacto de objeto cortante ou perfurante",
    "Y019": "Agressão por impacto de objeto contundente",
    "Y020": "Agressão por impacto de veículo a motor",
    "Y021": "Agressão por impacto de outro veículo",
    "Y022": "Agressão por impacto de veículo não especificado",
    "Y023": "Agressão por explosão de gás ou vapor",
    "Y024": "Agressão por explosão de outro objeto",
    "Y025": "Agressão por impacto de veículo ferroviário",
    "Y026": "Agressão por impacto de veículo não motorizado",
    "Y027": "Agressão por impacto de objeto em movimento",
    "Y028": "Agressão por impacto de objeto fixo",
    "Y029": "Agressão por impacto de objeto cortante ou perfurante",
    "Y030": "Agressão por força corporal",
    "Y031": "Agressão sexual não especificada",
    "Y032": "Agressão por outro meio físico",
    "Y033": "Agressão por outro meio químico",
    "Y034": "Agressão por outro meio mecânico",
    "Y035": "Agressão por outro meio desconhecido",
    "Y036": "Agressão por outro meio não especificado",
    "Y037": "Outras agressões físicas",
    "Y038": "Agressão sexual por outro meio",
    "Y039": "Agressão sexual",
    "Y040": "Outras agressões físicas",
    "Y041": "Agressão sexual por outro meio",
    "Y042": "Agressão sexual",
    "Y043": "Agressão sexual",
    "Y044": "Agressão sexual por outro meio",
    "Y045": "Agressão sexual",
    "Y046": "Agressão sexual por outro meio",
    "Y047": "Agressão sexual",
    "Y048": "Agressão sexual por outro meio",
    "Y049": "Agressão sexual",
    "Y050": "Agressão sexual por força física",
    "Y051": "Agressão sexual por outro meio",
    "Y052": "Agressão sexual",
    "Y053": "Agressão sexual por outro meio",
    "Y054": "Agressão sexual",
    "Y055": "Agressão sexual por outro meio",
    "Y056": "Agressão sexual",
    "Y057": "Agressão sexual por outro meio",
    "Y058": "Agressão sexual",
    "Y059": "Agressão sexual por outro meio",
    "Y060": "Negligência e abandono pelo cônjuge",
    "Y061": "Negligência e abandono pelos pais",
    "Y062": "Negligência e abandono por conhecido",
    "Y063": "Negligência e abandono por outra pessoa",
    "Y064": "Negligência e abandono por pessoa não especificada",
    "Y065": "Síndromes de maus tratos pelo cônjuge",
    "Y066": "Síndromes de maus tratos pelos pais",
    "Y067": "Síndromes de maus tratos por conhecido",
    "Y068": "Síndromes de maus tratos por autoridade oficial",
    "Y069": "Síndromes de maus tratos por outra pessoa",
    "Y070": "Síndromes de maus tratos pelo cônjuge",
    "Y071": "Síndromes de maus tratos pelos pais",
    "Y072": "Síndromes de maus tratos por conhecido",
    "Y073": "Síndromes de maus tratos por autoridade oficial",
    "Y074": "Síndromes de maus tratos por outra pessoa",
    "Y075": "Síndromes de maus tratos por pessoa não especificada",
    "Y076": "Síndromes de maus tratos por pessoa não especificada",
    "Y077": "Síndromes de maus tratos por pessoa não especificada",
    "Y078": "Síndromes de maus tratos por pessoa não especificada",
    "Y079": "Síndromes de maus tratos por pessoa não especificada",
    "Y080": "Agressão por outros meios especificados",
    "Y081": "Agressão por outros meios físicos",
    "Y082": "Agressão por outros meios químicos",
    "Y083": "Agressão por outros meios mecânicos",
    "Y084": "Agressão por outros meios desconhecidos",
    "Y085": "Agressão por outros meios especificados",
    "Y086": "Agressão por outros meios físicos",
    "Y087": "Agressão por outros meios químicos",
    "Y088": "Agressão por outros meios mecânicos",
    "Y089": "Agressão por outros meios desconhecidos",
    "Y090": "Agressão por meios não especificados",
    "Y350": "Intervenção legal envolvendo uso de armas de fogo",
    "Y351": "Intervenção legal envolvendo uso de armas brancas",
    "Y352": "Intervenção legal envolvendo uso de força corporal",
    "Y353": "Intervenção legal envolvendo uso de outros meios",
    "Y354": "Intervenção legal envolvendo uso de meios não especificados",
    "Y355": "Intervenção legal envolvendo uso de armas de fogo",
    "Y356": "Intervenção legal envolvendo uso de armas brancas",
    "Y357": "Intervenção legal envolvendo uso de força corporal",
    "Y358": "Intervenção legal envolvendo uso de outros meios",
    "Y359": "Intervenção legal envolvendo uso de meios não especificados",
}

# ------------------- Mapeamentos para CASE WHEN no DuckDB -------------------
def _build_case_when(coluna: str, mapa: dict, fallback: str = "NULL") -> str:
    """Gera um bloco CASE WHEN a partir de um dicionário Python."""
    branches = "\n            ".join(
        f"WHEN {coluna} = '{k}' THEN '{v}'" for k, v in mapa.items()
    )
    return f"CASE\n            {branches}\n            ELSE {fallback}\n        END"


mapa_sexo    = {"1": "MASCULINO", "2": "FEMININO"}
mapa_raca    = {"1": "BRANCA", "2": "PRETA", "3": "AMARELA", "4": "PARDA", "5": "INDIGENA"}
mapa_estciv  = {"1": "SOLTEIRA", "2": "CASADA", "3": "VIUVA", "4": "DIVORCIADA", "5": "UNIÃO ESTAVEL"}
mapa_loccoro = {
    "1": "HOSPITAL", "2": "OUTROS ESTABELECIMENTOS DE SAUDE",
    "3": "DOMICILIO", "4": "VIA PUBLICA", "5": "OUTROS", "6": "ALDEIA INDIGENA",
}
mapa_circobito = {"1": "ACIDENTE", "2": "SUICIDIO", "3": "HOMICIDIO", "4": "OUTROS"}
mapa_gestante  = {"1": "SIM", "2": "NAO"}
mapa_puerperio = {
    "1": "SIM ATÉ 42 DIAS APOS O PARTO",
    "2": "SIM ATÉ 43 DIAS A 1 ANO APOS O PARTO",
    "3": "NAO",
}

# ------------------- Caminhos -------------------
CURRENT_DIR  = Path(__file__).resolve().parent
BASE_DIR     = CURRENT_DIR.parent.parent.parent
DBC_DIR      = BASE_DIR / "data" / "landing" / "datasus" / "dbc_sim_causas_externas"
PROCESSED_DIR = BASE_DIR / "data" / "processed" / "datasus_sim"


# ------------------- Pipeline principal -------------------
def processar_feminicidio_dbc(dbc_dir: Path, caminho_saida: Path) -> None:
    arquivos_dbc = sorted(f for f in os.listdir(dbc_dir) if f.lower().endswith(".dbc"))

    if not arquivos_dbc:
        logger.warning(f"Nenhum arquivo .dbc encontrado em {dbc_dir}.")
        return

    logger.info(f"Arquivos encontrados: {len(arquivos_dbc)}")

    temp_dir = dbc_dir / "temp_parquets"
    temp_dir.mkdir(exist_ok=True)

    logger.info("Fase 1: DBC → Parquets temporários (pré-filtro SEXO=2)...")

    causas_validas = set(codigos_agressao.keys())
    parquets_gerados = []

    for idx, arquivo in enumerate(arquivos_dbc, 1):
        caminho_dbc = str(dbc_dir / arquivo)
        caminho_dbf = caminho_dbc.replace(".DBC", ".DBF").replace(".dbc", ".dbf")
        nome_parquet = arquivo.replace(".dbc", ".parquet").replace(".DBC", ".parquet")
        caminho_parquet = str(temp_dir / nome_parquet)

        if os.path.exists(caminho_parquet):
            parquets_gerados.append(caminho_parquet)
            logger.info(f"[{idx}/{len(arquivos_dbc)}] [SKIP] {arquivo}")
            continue

        logger.info(f"[{idx}/{len(arquivos_dbc)}] Convertendo {arquivo}...")

        try:
            if os.path.exists(caminho_dbf):
                os.remove(caminho_dbf)

            datasus_dbc.decompress(caminho_dbc, caminho_dbf)

            table = DBF(caminho_dbf, encoding='latin1')

            parquet_writer = None
            chunk = []
            chunk_size = 250_000

            for record in table:
                chunk.append(dict(record))

                if len(chunk) >= chunk_size:
                    df_chunk = pd.DataFrame(chunk).astype(str)
                    chunk = []

                    if 'SEXO' in df_chunk.columns and 'CAUSABAS' in df_chunk.columns:
                        df_chunk = df_chunk[
                            (df_chunk['SEXO'] == '2') &
                            (df_chunk['CAUSABAS'].isin(causas_validas))
                        ]

                    if df_chunk.empty:
                        del df_chunk
                        gc.collect()
                        continue

                    table_pa = pa.Table.from_pandas(df_chunk, preserve_index=False)

                    if parquet_writer is None:
                        parquet_writer = pq.ParquetWriter(caminho_parquet, table_pa.schema)

                    parquet_writer.write_table(table_pa)

                    del df_chunk, table_pa
                    gc.collect()

            # 🔥 processa resto final
            if chunk:
                df_chunk = pd.DataFrame(chunk).astype(str)

                if 'SEXO' in df_chunk.columns and 'CAUSABAS' in df_chunk.columns:
                    df_chunk = df_chunk[
                        (df_chunk['SEXO'] == '2') &
                        (df_chunk['CAUSABAS'].isin(causas_validas))
                    ]

                if not df_chunk.empty:
                    table_pa = pa.Table.from_pandas(df_chunk, preserve_index=False)

                    if parquet_writer is None:
                        parquet_writer = pq.ParquetWriter(caminho_parquet, table_pa.schema)

                    parquet_writer.write_table(table_pa)

                    del df_chunk, table_pa
                    gc.collect()

            if parquet_writer:
                parquet_writer.close()
                parquets_gerados.append(caminho_parquet)
            else:
                logger.info(f"  → Nenhum registro válido em {arquivo}, parquet não criado.")

            os.remove(caminho_dbf)

        except Exception as e:
            logger.error(f"❌ Falha ao converter {arquivo}: {e}")
            if os.path.exists(caminho_dbf):
                os.remove(caminho_dbf)

    if not parquets_gerados:
        logger.error("Nenhum parquet gerado. Abortando.")
        shutil.rmtree(temp_dir)
        return

    # ----------------------------------------------------------
    # FASE 2: DuckDB
    # ----------------------------------------------------------
    logger.info("Fase 2: Consolidando parquets...")

    padrao_leitura = str(temp_dir / "*.parquet")

    case_sexo      = _build_case_when("SEXO", mapa_sexo)
    case_raca      = _build_case_when("RACACOR", mapa_raca)
    case_estciv    = _build_case_when("ESTCIV", mapa_estciv)
    case_loccoro   = _build_case_when("LOCOCOR", mapa_loccoro)
    case_circobito = _build_case_when("CIRCOBITO", mapa_circobito)
    case_gestante  = _build_case_when("OBITOGRAV", mapa_gestante)
    case_puerperio = _build_case_when("OBITOPUERP", mapa_puerperio)

    map_entries = ", ".join(f"'{k}': '{v}'" for k, v in codigos_agressao.items())
    case_descricao = f"MAP {{{map_entries}}}[CAUSABAS]"

    causas_tuple = "('" + "','".join(causas_validas) + "')"

    query = f"""
        COPY (
            SELECT
                DTNASC AS DT_NASCIMENTO,
                DTOBITO AS DT_OBITO,
                DTCADASTRO AS DT_CADASTRO_OBITO,
                HORAOBITO AS HORA_OBITO,
                {case_sexo} AS SEXO,
                {case_raca} AS RACA_COR,
                {case_estciv} AS EST_CIVIL,
                CODMUNRES AS COD_MUNICIPIO_RESID,
                CODMUNOCOR AS COD_MUNICIPIO_OBITO,
                {case_loccoro} AS LOCAL_OCORRENCIA_OBITO,
                CAUSABAS AS CAUSA_BASICA,
                {case_circobito} AS TIPO_OBITO,
                {case_descricao} AS DESCRICAO,
                {case_gestante} AS GESTANTE,
                {case_puerperio} AS PUERPERIO
            FROM read_parquet('{padrao_leitura}', union_by_name=True)
            WHERE SEXO = '2'
              AND CAUSABAS IN {causas_tuple}
        )
        TO '{str(caminho_saida)}' (HEADER, DELIMITER ',');
    """

    con = None
    try:
        temp_duckdb = BASE_DIR / "tmp" / "duckdb"
        temp_duckdb.mkdir(parents=True, exist_ok=True)
        caminho_saida.parent.mkdir(parents=True, exist_ok=True)

        con = duckdb.connect(database=':memory:', config={
            'temp_directory': str(temp_duckdb),
            'memory_limit': '4GB',
        })

        con.execute("PRAGMA threads=4;")
        con.execute(query)

        contagem = con.execute(
            f"SELECT COUNT(*) FROM read_parquet('{padrao_leitura}')"
        ).fetchone()[0]

        logger.info(f"Concluído! {contagem} registros salvos.")

    except Exception as e:
        logger.error(f"❌ Falha no DuckDB: {e}")

    finally:
        if con:
            con.close()

    shutil.rmtree(temp_dir)
    logger.info("Diretório temporário removido.")


# ------------------- Entrypoint -------------------
if __name__ == "__main__":
    caminho_saida = PROCESSED_DIR / "feminicidio_serie_historica.csv"
    processar_feminicidio_dbc(DBC_DIR, caminho_saida)