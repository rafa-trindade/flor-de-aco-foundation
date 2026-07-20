"""Caminhos centrais do projeto, usados por extract/process/load.

LANDING_DIR e PROCESSED_DIR são scratch space temporário: arquivos passam
por elas durante o processamento e são apagados após publicação no bucket
(ver scripts.common.bucket_sync). Fontes como o SIM acumulam vários GB
durante uma execução -- daí o override de disco via .env.

MANUAL_DIR e PUBLISH_CACHE_DIR são persistentes e nunca apagadas:

- MANUAL_DIR: fontes sem fetch automatizado (DataSenado, PNS/IBGE,
  geolocalização das macrorregiões). Ficam FORA de landing/processed de
  propósito -- são insumo que só se recupera baixando de novo na mão, não
  pode correr risco de cair numa limpeza de scratch.
- PUBLISH_CACHE_DIR: cópia local do dataset publicado no Kaggle,
  reaproveitada entre execuções para baixar do bucket só o que mudou.

Overrides disponíveis no .env:
    FLOR_DE_ACO_LANDING_DIR=D:\\flor-de-aco\\landing
    FLOR_DE_ACO_PROCESSED_DIR=D:\\flor-de-aco\\processed
    FLOR_DE_ACO_MANUAL_DIR=D:\\flor-de-aco\\manual
    FLOR_DE_ACO_PUBLISH_CACHE_DIR=D:\\flor-de-aco\\kaggle-publish-cache
    DUCKDB_TEMP_DIR=D:\\flor-de-aco\\.duckdb_temp
"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# load_dotenv aqui (não só em env.py): paths.py é importado antes de env.py
# em várias cadeias de import, e o módulo fica em cache após a primeira
# execução -- sem isso os overrides abaixo não enxergam o .env.
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"


def _dir_com_override(env_var: str, padrao: Path) -> Path:
    override = os.environ.get(env_var)
    return Path(override) if override else padrao


LANDING_DIR = _dir_com_override("FLOR_DE_ACO_LANDING_DIR", DATA_DIR / "landing")
PROCESSED_DIR = _dir_com_override("FLOR_DE_ACO_PROCESSED_DIR", DATA_DIR / "processed")
MANUAL_DIR = _dir_com_override("FLOR_DE_ACO_MANUAL_DIR", DATA_DIR / "manual")
PUBLISH_CACHE_DIR = _dir_com_override("FLOR_DE_ACO_PUBLISH_CACHE_DIR", DATA_DIR / "kaggle_publish_cache")
DUCKDB_TEMP_DIR = _dir_com_override("DUCKDB_TEMP_DIR", DATA_DIR / ".duckdb_temp")

# Subpastas fixas de MANUAL_DIR -- referenciadas pelos process das fontes
MANUAL_MACROREGIAO_DIR = MANUAL_DIR / "macroregiao"
MANUAL_DATASEN_DIR = MANUAL_DIR / "datasen"
MANUAL_DATASEN_DICT_DIR = MANUAL_DATASEN_DIR / "dict"
MANUAL_PNS_DIR = MANUAL_DIR / "ibge" / "pns"

for _dir in (LANDING_DIR, PROCESSED_DIR, MANUAL_DIR, PUBLISH_CACHE_DIR, DUCKDB_TEMP_DIR,
             MANUAL_MACROREGIAO_DIR, MANUAL_DATASEN_DIR, MANUAL_DATASEN_DICT_DIR, MANUAL_PNS_DIR):
    _dir.mkdir(parents=True, exist_ok=True)