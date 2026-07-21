"""Acesso ao S3/MinIO.

O bucket é a fonte da verdade (SSOT). O manifesto mapeia casos onde 
múltiplos arquivos-fonte consolidam em um único output sem chave 1-pra-1.
"""
import hashlib
import json
import logging
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from scripts.common import env

logger = logging.getLogger(__name__)

_client = None


def get_s3_client():

    global _client
    if _client is None:
        faltando = env.validar_minio()
        if faltando:
            raise RuntimeError(
                f"Variáveis do MinIO ausentes no .env: {', '.join(faltando)}. "
                f"Veja .env.example."
            )
        _client = boto3.client(
            "s3",
            endpoint_url=env.MINIO_ENDPOINT,
            aws_access_key_id=env.MINIO_ROOT_USER,
            aws_secret_access_key=env.MINIO_ROOT_PASSWORD,
        )
        try:
            _client.head_bucket(Bucket=env.MINIO_BUCKET)
        except ClientError:
            logger.info(f"Bucket '{env.MINIO_BUCKET}' não encontrado. Criando...")
            _client.create_bucket(Bucket=env.MINIO_BUCKET)
    return _client


def _tamanho_remoto(s3_key: str) -> int | None:
    s3 = get_s3_client()
    try:
        return s3.head_object(Bucket=env.MINIO_BUCKET, Key=s3_key)["ContentLength"]
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return None
        raise


def _hash_remoto_md5(s3_key: str) -> str | None:
    """ETag do objeto. Só é MD5 real em upload simples (não multipart) --
    usar como sinal adicional, não garantia."""
    s3 = get_s3_client()
    try:
        return s3.head_object(Bucket=env.MINIO_BUCKET, Key=s3_key)["ETag"].strip('"')
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return None
        raise


def _hash_local_md5(caminho: Path) -> str:
    md5 = hashlib.md5()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(8 * 1024 * 1024), b""):
            md5.update(bloco)
    return md5.hexdigest()


def already_in_bucket(s3_key: str, tamanho_local_esperado: int | None = None,
                       caminho_local_para_hash: Path | None = None) -> bool:
    """O tamanho é suficiente se a origem reportar metadados confiáveis.
    Passar `caminho_local_para_hash` força uma validação estrita por MD5.
    """
    tamanho_remoto = _tamanho_remoto(s3_key)
    if tamanho_remoto is None:
        return False

    if tamanho_local_esperado is not None and tamanho_remoto != tamanho_local_esperado:
        return False

    if caminho_local_para_hash is not None and caminho_local_para_hash.exists():
        if _hash_remoto_md5(s3_key) != _hash_local_md5(caminho_local_para_hash):
            return False

    return True


def upload_and_cleanup(caminho_local: Path, s3_key: str, apagar_local: bool = True) -> bool:
    """Nota: apagar_local=False deve ser usado exclusivamente para depuração."""
    s3 = get_s3_client()
    logger.info(f"[UPLOAD] Enviando {s3_key} ...")
    try:
        s3.upload_file(str(caminho_local), env.MINIO_BUCKET, s3_key)
        logger.info(f"[UPLOAD OK] {s3_key}")
    except Exception as e:
        logger.error(f"[ERRO UPLOAD] '{s3_key}': {e}")
        return False

    if apagar_local:
        try:
            Path(caminho_local).unlink()
        except FileNotFoundError:
            pass

    return True


def _chave_manifesto(pasta_bucket: str) -> str:
    return f"{pasta_bucket}/_manifest.json"


def carregar_manifesto(pasta_bucket: str) -> dict[str, int]:
    """Retorna o schema: dict[NOME_ARQUIVO_MAIUSCULO, tamanho_em_bytes]."""
    s3 = get_s3_client()
    try:
        resposta = s3.get_object(Bucket=env.MINIO_BUCKET, Key=_chave_manifesto(pasta_bucket))
        bruto = json.loads(resposta["Body"].read())
        return {k.upper(): v for k, v in bruto.items()}
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return {}
        raise


def salvar_manifesto(pasta_bucket: str, manifesto: dict[str, int]):
    """Deve ser chamado para atualizar o estado apenas após publicar um output novo."""
    s3 = get_s3_client()
    chave = _chave_manifesto(pasta_bucket)
    normalizado = {k.upper(): v for k, v in manifesto.items()}
    s3.put_object(
        Bucket=env.MINIO_BUCKET,
        Key=chave,
        Body=json.dumps(normalizado, indent=2, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
    )
    logger.info(f"[MANIFESTO] {chave} atualizado ({len(normalizado)} arquivo(s) registrados).")


def listar_objetos(prefixo: str = "") -> dict[str, int]:
    """Retorna mapeamento: dict[s3_key, tamanho_em_bytes]."""
    s3 = get_s3_client()
    paginator = s3.get_paginator("list_objects_v2")
    objetos = {}
    kwargs = {"Bucket": env.MINIO_BUCKET}
    if prefixo:
        kwargs["Prefix"] = prefixo
    for pagina in paginator.paginate(**kwargs):
        for obj in pagina.get("Contents", []):
            objetos[obj["Key"]] = obj["Size"]
    return objetos