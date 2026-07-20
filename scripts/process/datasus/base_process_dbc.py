"""Conversão .dbc -> Parquet com publicação incremental no bucket.

Fluxo: DBC -> DBF -> Parquets intermediários -> consolidação DuckDB ->
merge com o Parquet já publicado -> upload -> limpeza local.

A coluna _ARQUIVO_ORIGEM é gravada em cada linha para permitir o merge
incremental: ao reprocessar um arquivo revisado pelo DATASUS, as linhas
antigas dele são removidas antes de inserir as novas, sem duplicar.
"""
import os
import gc
import time
import shutil
import logging
from pathlib import Path
from typing import Callable

import datasus_dbc
from simpledbf import Dbf5
import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from scripts.common.paths import DUCKDB_TEMP_DIR
from scripts.common import simpledbf_patch  # corrige datas zeradas (00000000)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

ROW_GROUP_SIZE = 250_000
MEMORY_LIMIT = '4GB'
THREADS = 4

# Strings que o astype(str) produz a partir de valores ausentes. O
# comportamento varia por versão do pandas (2.x gera 'nan' literal, 3.x
# preserva NaN), então a limpeza roda sempre.
_STRINGS_NULAS = ["nan", "NaN", "NaT", "None", "", "<NA>"]


def _conectar_duckdb():
    DUCKDB_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(database=':memory:', config={
        'temp_directory': str(DUCKDB_TEMP_DIR),
        'memory_limit': MEMORY_LIMIT,
    })
    con.execute(f"PRAGMA threads={THREADS};")
    return con


def listar_dbc_deduplicados(dbc_dir: Path) -> list[str]:
    """Lista .dbc removendo duplicatas por maiúscula/minúscula (X.DBC e X.dbc)."""
    vistos = set()
    arquivos = []
    for f in sorted(os.listdir(dbc_dir)):
        if not f.lower().endswith(".dbc"):
            continue
        chave = f.upper()
        if chave in vistos:
            continue
        vistos.add(chave)
        arquivos.append(f)
    return arquivos


def processar_diretorio_dbc(dbc_dir: Path, parquet_final_path: Path,
                             filtro_chunk: Callable | None = None,
                             apagar_dbc: bool = True) -> bool:
    """Converte .dbc do diretório para um Parquet consolidado.

    filtro_chunk: recebe e devolve um DataFrame, aplicado por chunk antes
    de escrever. Usado para pré-filtrar (ex: SEXO=2 no SIM) e evitar
    carregar dado irrelevante nas fases seguintes.
    """
    arquivos_dbc = listar_dbc_deduplicados(dbc_dir)
    if not arquivos_dbc:
        logger.warning(f"Nenhum arquivo .dbc encontrado em {dbc_dir}.")
        return False

    logger.info(f"Arquivos encontrados: {len(arquivos_dbc)}")
    temp_dir = dbc_dir / "temp_parquets"
    temp_dir.mkdir(exist_ok=True)

    logger.info("Fase 1: Convertendo DBCs para Parquets intermediários...")
    parquets_gerados = []

    for idx, arquivo in enumerate(arquivos_dbc, 1):
        caminho_dbc = str(dbc_dir / arquivo)
        caminho_dbf = caminho_dbc.replace(".DBC", ".DBF").replace(".dbc", ".dbf")
        caminho_parquet = str(temp_dir / arquivo.replace(".dbc", ".parquet").replace(".DBC", ".parquet"))

        if os.path.exists(caminho_parquet):
            parquets_gerados.append(caminho_parquet)
            logger.info(f"[{idx}/{len(arquivos_dbc)}] [SKIP] {arquivo} (parquet temp já existe)")
            continue

        logger.info(f"[{idx}/{len(arquivos_dbc)}] Convertendo {arquivo}...")
        dbf = None
        try:
            if os.path.exists(caminho_dbf):
                os.remove(caminho_dbf)
            datasus_dbc.decompress(caminho_dbc, caminho_dbf)

            dbf = Dbf5(caminho_dbf, codec='latin1')
            parquet_writer = None

            for df_chunk in dbf.to_dataframe(chunksize=250_000):
                # astype(str) uniformiza o schema entre anos (o DBF varia
                # tipo entre competências), mas transforma NaN na string
                # literal 'nan' -- pior que NULL, porque IS NULL não pega
                # e qualquer parse/cálculo erra em silêncio.
                df_chunk = df_chunk.astype(str)
                df_chunk = df_chunk.mask(df_chunk.isin(_STRINGS_NULAS))

                if filtro_chunk is not None:
                    df_chunk = filtro_chunk(df_chunk)
                    if df_chunk.empty:
                        del df_chunk
                        gc.collect()
                        continue

                df_chunk["_ARQUIVO_ORIGEM"] = arquivo
                table = pa.Table.from_pandas(df_chunk, preserve_index=False)

                if parquet_writer is None:
                    parquet_writer = pq.ParquetWriter(caminho_parquet, table.schema)
                parquet_writer.write_table(table)

                del df_chunk, table
                gc.collect()

            if parquet_writer:
                parquet_writer.close()
                parquets_gerados.append(caminho_parquet)
            else:
                logger.info(f"  -> nenhum registro válido em {arquivo}, parquet não criado.")

            dbf.f.close()  # simpledbf não fecha sozinho (impede delete no Windows)
            os.remove(caminho_dbf)
            if apagar_dbc:
                os.remove(caminho_dbc)

        except Exception as e:
            logger.error(f"Falha ao converter {arquivo}: {e}")
            try:
                if dbf is not None:
                    dbf.f.close()
            except (AttributeError, ValueError):
                pass
            if os.path.exists(caminho_dbf):
                os.remove(caminho_dbf)

    if not parquets_gerados:
        logger.error("Nenhum arquivo convertido com sucesso.")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False

    logger.info("Fase 2: Consolidando Parquets intermediários (DuckDB)...")
    padrao = str(temp_dir / "*.parquet")
    parquet_final_path.parent.mkdir(parents=True, exist_ok=True)

    con = None
    sucesso = False
    try:
        con = _conectar_duckdb()
        con.execute(f"""
            COPY (SELECT * FROM read_parquet('{padrao}', union_by_name=True))
            TO '{parquet_final_path}' (FORMAT PARQUET, ROW_GROUP_SIZE {ROW_GROUP_SIZE});
        """)
        contagem = con.execute(f"SELECT COUNT(*) FROM read_parquet('{padrao}')").fetchone()[0]
        logger.info(f"Consolidado: {contagem} registros em {parquet_final_path.name}")
        sucesso = True
    except Exception as e:
        logger.error(f"Falha no DuckDB durante a consolidação: {e}")
    finally:
        if con is not None:
            con.close()

    _limpar_residuos(dbc_dir, temp_dir)
    return sucesso


def _limpar_residuos(dbc_dir: Path, temp_dir: Path):
    """Remove .dbf órfãos e a pasta temporária.

    No Windows os.remove() pode ser aceito sem erro mas não efetivar se
    algum handle continuar aberto (datasus_dbc.decompress é lib C e nem
    sempre libera na hora). Daí a varredura no fim, com retry.
    """
    for residuo in list(dbc_dir.glob("*.dbf")) + list(dbc_dir.glob("*.DBF")):
        for tentativa in range(3):
            try:
                residuo.unlink()
                logger.info(f"Resíduo removido: {residuo.name}")
                break
            except FileNotFoundError:
                break
            except OSError:
                if tentativa < 2:
                    time.sleep(0.5)
                else:
                    logger.warning(f"Não consegui remover {residuo.name} (handle preso). Será limpo na próxima execução.")

    for tentativa in range(3):
        if not temp_dir.exists():
            break
        shutil.rmtree(temp_dir, ignore_errors=True)
        if temp_dir.exists():
            time.sleep(0.5)


def processar_e_publicar_incremental(dbc_dir: Path, pasta_bucket: str, nome_arquivo_final: str,
                                      filtro_chunk: Callable | None = None,
                                      query_transformacao: str | None = None) -> bool:
    """Processa .dbc novos e mescla com o Parquet já publicado.

    query_transformacao: SELECT aplicado sobre os dados novos antes do
    merge. Use o token __ORIGEM__ onde entra a fonte -- não use {} de
    format(), que colide com a sintaxe MAP {...} do DuckDB.
    """
    from botocore.exceptions import ClientError

    from scripts.common.bucket_sync import get_s3_client, upload_and_cleanup
    from scripts.common import env

    s3_key = f"{pasta_bucket}/{nome_arquivo_final}"

    arquivos_dbc = listar_dbc_deduplicados(dbc_dir)
    if not arquivos_dbc:
        logger.info(f"Nenhum .dbc novo/alterado em {dbc_dir} -- nada a processar.")
        return False

    nomes_novos = set(arquivos_dbc)
    parquet_novos = dbc_dir / "_novos_temp.parquet"

    if not processar_diretorio_dbc(dbc_dir, parquet_novos, filtro_chunk=filtro_chunk):
        return False

    if query_transformacao:
        parquet_transformado = dbc_dir / "_novos_transformado.parquet"
        select = query_transformacao.replace("__ORIGEM__", f"read_parquet('{parquet_novos}')")
        con = _conectar_duckdb()
        try:
            con.execute(f"""
                COPY ({select})
                TO '{parquet_transformado}' (FORMAT PARQUET, ROW_GROUP_SIZE {ROW_GROUP_SIZE});
            """)
        finally:
            con.close()
        parquet_novos.unlink(missing_ok=True)
        parquet_novos = parquet_transformado

    existente = dbc_dir / "_existente_temp.parquet"
    tem_existente = False
    s3 = get_s3_client()
    try:
        s3.download_file(env.MINIO_BUCKET, s3_key, str(existente))
        tem_existente = True
        logger.info(f"Parquet publicado encontrado em {s3_key} -- mesclando.")
    except ClientError as e:
        codigo = e.response.get("Error", {}).get("Code", "")
        if codigo in ("404", "NoSuchKey"):
            logger.info(f"Nada publicado ainda em {s3_key} -- primeira publicação.")
        else:
            # Qualquer outro erro (rede, credencial, permissão) NÃO pode
            # virar "primeira publicação": seguir adiante sobrescreveria o
            # histórico já publicado com apenas os arquivos desta rodada.
            logger.error(f"Falha ao baixar {s3_key} para merge ({codigo}): {e}")
            return False

    final = dbc_dir / nome_arquivo_final
    con = _conectar_duckdb()
    try:
        if tem_existente:
            lista = ", ".join(f"'{n}'" for n in nomes_novos)
            query = f"""
                COPY (
                    SELECT * FROM read_parquet('{existente}')
                    WHERE _ARQUIVO_ORIGEM NOT IN ({lista})
                    UNION ALL BY NAME
                    SELECT * FROM read_parquet('{parquet_novos}')
                ) TO '{final}' (FORMAT PARQUET, ROW_GROUP_SIZE {ROW_GROUP_SIZE});
            """
        else:
            query = f"""
                COPY (SELECT * FROM read_parquet('{parquet_novos}'))
                TO '{final}' (FORMAT PARQUET, ROW_GROUP_SIZE {ROW_GROUP_SIZE});
            """
        con.execute(query)
        contagem = con.execute(f"SELECT COUNT(*) FROM read_parquet('{final}')").fetchone()[0]
        logger.info(f"{contagem} registros no Parquet final ({nome_arquivo_final}).")
    except Exception as e:
        logger.error(f"Falha ao mesclar: {e}")
        return False
    finally:
        con.close()

    parquet_novos.unlink(missing_ok=True)
    if tem_existente:
        existente.unlink(missing_ok=True)

    return upload_and_cleanup(final, s3_key)


def processar_fonte_ftp_incremental(dbc_dir: Path, pasta_bucket: str, nome_arquivo_final: str,
                                     filtro_chunk: Callable | None = None,
                                     query_transformacao: str | None = None) -> int:
    """Orquestra process + atualização do manifesto. Retorna exit code."""
    from scripts.common import exit_codes
    from scripts.common.bucket_sync import carregar_manifesto, salvar_manifesto

    if not dbc_dir.exists():
        logger.info(f"{dbc_dir} não existe -- nada a processar.")
        return exit_codes.SEM_NOVIDADE

    arquivos_presentes = {
        f: (dbc_dir / f).stat().st_size
        for f in listar_dbc_deduplicados(dbc_dir)
    }
    if not arquivos_presentes:
        logger.info("Nenhum .dbc novo/alterado -- nada a processar.")
        return exit_codes.SEM_NOVIDADE

    sucesso = processar_e_publicar_incremental(
        dbc_dir, pasta_bucket, nome_arquivo_final,
        filtro_chunk=filtro_chunk, query_transformacao=query_transformacao,
    )
    if not sucesso:
        return exit_codes.ERRO

    manifesto = carregar_manifesto(pasta_bucket)
    manifesto.update({k.upper(): v for k, v in arquivos_presentes.items()})
    salvar_manifesto(pasta_bucket, manifesto)

    return exit_codes.SUCESSO