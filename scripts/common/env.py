"""Variáveis de ambiente e configuração de logging."""
import logging
import os

from scripts.common.paths import BASE_DIR  # load_dotenv acontece lá

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT")
MINIO_ROOT_USER = os.environ.get("MINIO_ROOT_USER")
MINIO_ROOT_PASSWORD = os.environ.get("MINIO_ROOT_PASSWORD")
MINIO_BUCKET = os.environ.get("MINIO_BUCKET")

KAGGLE_DIR = BASE_DIR / ".kaggle"
KAGGLE_JSON = KAGGLE_DIR / "kaggle.json"

# Sem isso, logger.info() dos módulos comuns não aparece quando um script
# roda sozinho via python -m.
logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s - %(levelname)s - %(message)s",
)
for _ruidoso in ("botocore", "boto3", "urllib3"):
    logging.getLogger(_ruidoso).setLevel(logging.WARNING)


def validar_minio() -> list[str]:
    """Nomes das variáveis obrigatórias do MinIO que estão faltando."""
    obrigatorias = {
        "MINIO_ENDPOINT": MINIO_ENDPOINT,
        "MINIO_ROOT_USER": MINIO_ROOT_USER,
        "MINIO_ROOT_PASSWORD": MINIO_ROOT_PASSWORD,
        "MINIO_BUCKET": MINIO_BUCKET,
    }
    return [nome for nome, valor in obrigatorias.items() if not valor]