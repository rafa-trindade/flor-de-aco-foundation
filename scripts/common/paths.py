"""Caminhos do projeto. Overrides via .env (ver env.example).

LANDING_DIR/PROCESSED_DIR são scratch: apagados após publicação.
MANUAL_DIR e PUBLISH_CACHE_DIR são persistentes.
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