"""
Caminhos centrais do projeto, usados por todos os módulos de extract/process.

"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

DATA_DIR = BASE_DIR / "data"
LANDING_DIR = DATA_DIR / "landing"
PROCESSED_DIR = DATA_DIR / "processed"

LANDING_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)