"""Variáveis de ambiente centrais, lidas uma vez só.
"""
import os

from scripts.common.paths import BASE_DIR 

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT")
MINIO_ROOT_USER = os.environ.get("MINIO_ROOT_USER")
MINIO_ROOT_PASSWORD = os.environ.get("MINIO_ROOT_PASSWORD")
MINIO_BUCKET = os.environ.get("MINIO_BUCKET")

KAGGLE_DIR = BASE_DIR / ".kaggle"
KAGGLE_JSON = KAGGLE_DIR / "kaggle.json"


def validar_minio() -> list[str]:
    """Retorna lista de variáveis obrigatórias do MinIO que estão faltando."""
    obrigatorias = {
        "MINIO_ENDPOINT": MINIO_ENDPOINT,
        "MINIO_ROOT_USER": MINIO_ROOT_USER,
        "MINIO_ROOT_PASSWORD": MINIO_ROOT_PASSWORD,
        "MINIO_BUCKET": MINIO_BUCKET,
    }
    return [nome for nome, valor in obrigatorias.items() if not valor]