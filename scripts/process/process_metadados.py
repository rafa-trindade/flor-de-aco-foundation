"""Gera o manifesto de arquivos publicados no bucket.

Lê apenas o rodapé de metadados de cada Parquet -- não baixa o arquivo
inteiro, o que importa quando a maior base passa de 3 milhões de linhas.

O CSV resultante fica no bucket e serve de índice para quem consome:
o que existe, de que fonte veio, quantos registros tem e quando mudou.
"""
import csv
import logging
import sys
from collections import defaultdict

import pyarrow.fs as pafs
import pyarrow.parquet as pq

from scripts.common import env, exit_codes
from scripts.common.bucket_sync import get_s3_client
from scripts.common.paths import DATA_DIR
from scripts.config.fontes import FONTES

logger = logging.getLogger(__name__)

NOME_ARQUIVO_SAIDA = "flor-de-aco-metadados.csv"
CAMINHO_LOCAL = DATA_DIR / NOME_ARQUIVO_SAIDA

COLUNAS = [
    "arquivo",
    "diretorio",
    "fontes_relacionadas",
    "observacoes",
    "num_registros",
    "num_colunas",
    "tamanho_bytes",
    "ultima_atualizacao",
]

# Arquivos de controle interno: checkpoint do Datajud, manifesto de
# sincronização do FTP e o próprio CSV gerado aqui.
def _e_arquivo_de_controle(nome: str) -> bool:
    return (
        nome == NOME_ARQUIVO_SAIDA
        or nome == "_manifest.json"
        or nome.startswith("_checkpoint_")
    )


def _fontes_por_pasta() -> tuple[dict[str, str], dict[str, str]]:
    """Nome e nota das fontes, agrupados por pasta do bucket.

    Uma pasta pode ter mais de uma fonte (o datasus_sinan é uma só, mas
    nada impede que outras compartilhem prefixo), daí a junção por ' | '.
    """
    nomes = defaultdict(list)
    notas = defaultdict(list)
    for f in FONTES:
        nomes[f.pasta_bucket].append(f.nome)
        if getattr(f, "nota", None):
            notas[f.pasta_bucket].append(f.nota)
    return (
        {pasta: " | ".join(v) for pasta, v in nomes.items()},
        {pasta: " | ".join(v) for pasta, v in notas.items()},
    )


def _montar_s3_filesystem() -> pafs.S3FileSystem:
    endpoint = env.MINIO_ENDPOINT.replace("http://", "").replace("https://", "")
    esquema = "https" if env.MINIO_ENDPOINT.startswith("https://") else "http"
    return pafs.S3FileSystem(
        endpoint_override=endpoint,
        access_key=env.MINIO_ROOT_USER,
        secret_key=env.MINIO_ROOT_PASSWORD,
        scheme=esquema,
    )


def _metadados_parquet(s3_fs: pafs.S3FileSystem, bucket: str,
                       key: str) -> tuple[int | None, int | None]:
    """(num_registros, num_colunas) lidos do rodapé do Parquet.

    O ParquetFile lê só o footer, então o custo independe do tamanho da
    base -- é o que torna viável catalogar milhões de linhas.
    """
    try:
        pf = pq.ParquetFile(f"{bucket}/{key}", filesystem=s3_fs)
        return pf.metadata.num_rows, pf.metadata.num_columns
    except Exception as e:
        logger.warning(f"Não foi possível ler metadados de {key}: {e}")
        return None, None


def gerar_linhas(s3_client, s3_fs, bucket: str,
                 nomes: dict[str, str], notas: dict[str, str]) -> list[dict]:
    paginator = s3_client.get_paginator("list_objects_v2")
    linhas = []

    for pagina in paginator.paginate(Bucket=bucket):
        for obj in pagina.get("Contents", []):
            key = obj["Key"]
            nome_arquivo = key.rsplit("/", 1)[-1]
            if _e_arquivo_de_controle(nome_arquivo):
                continue

            pasta = key.split("/")[0] if "/" in key else ""

            num_registros = num_colunas = None
            if key.endswith(".parquet"):
                num_registros, num_colunas = _metadados_parquet(s3_fs, bucket, key)

            linhas.append({
                "arquivo": key,
                "diretorio": pasta,
                "fontes_relacionadas": nomes.get(pasta, "(não mapeado em fontes.py)"),
                "observacoes": notas.get(pasta, ""),
                "num_registros": num_registros,
                "num_colunas": num_colunas,
                "tamanho_bytes": obj["Size"],
                "ultima_atualizacao": obj["LastModified"].strftime("%Y-%m-%d %H:%M:%S"),
            })

    linhas.sort(key=lambda r: r["arquivo"])
    return linhas


def main() -> int:
    faltando = env.validar_minio()
    if faltando:
        logger.error(f"Variáveis do MinIO ausentes: {', '.join(faltando)}")
        return exit_codes.ERRO

    nomes, notas = _fontes_por_pasta()
    s3_client = get_s3_client()
    s3_fs = _montar_s3_filesystem()

    logger.info(f"Catalogando {env.MINIO_BUCKET}...")
    linhas = gerar_linhas(s3_client, s3_fs, env.MINIO_BUCKET, nomes, notas)

    if not linhas:
        logger.warning("Nenhum arquivo encontrado no bucket.")
        return exit_codes.SEM_NOVIDADE

    CAMINHO_LOCAL.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig para o Excel abrir os acentos corretamente sem
    # configuração adicional.
    with open(CAMINHO_LOCAL, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=COLUNAS)
        writer.writeheader()
        writer.writerows(linhas)

    s3_client.upload_file(str(CAMINHO_LOCAL), env.MINIO_BUCKET, NOME_ARQUIVO_SAIDA)

    nao_mapeadas = sorted({
        l["diretorio"] for l in linhas
        if l["fontes_relacionadas"].startswith("(não mapeado")
    })
    if nao_mapeadas:
        logger.warning(f"Pasta(s) sem Fonte em fontes.py: {nao_mapeadas}")

    sem_metadados = [l["arquivo"] for l in linhas
                     if l["arquivo"].endswith(".parquet") and l["num_registros"] is None]
    if sem_metadados:
        logger.warning(f"Parquet(s) sem metadados legíveis: {sem_metadados}")

    total = sum(l["num_registros"] or 0 for l in linhas)
    logger.info(
        f"{NOME_ARQUIVO_SAIDA} publicado na raiz do bucket: "
        f"{len(linhas)} arquivo(s), {total:,} registro(s) no total."
        .replace(",", ".")
    )
    return exit_codes.SUCESSO


if __name__ == "__main__":
    sys.exit(main())