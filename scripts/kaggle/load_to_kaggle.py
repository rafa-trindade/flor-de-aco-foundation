import json
import shutil
import logging
from pathlib import Path
from datetime import datetime
from kaggle.api.kaggle_api_extended import KaggleApi

from scripts.common.paths import BASE_DIR, DATA_DIR

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ======================================================================
# CONFIG
# ======================================================================

KAGGLE_JSON_PATH = BASE_DIR / ".kaggle" / "kaggle.json"
DATASET_NAME = 'feminicidio-br'

# ------------------------------------------------------------------
# FONTES
# ------------------------------------------------------------------
# Derivado do registro central em scripts/config/fontes.py -- adicionar uma
# fonte nova não exige mais editar esta lista manualmente, só a entrada em
# FONTES lá no registro.
from scripts.config.fontes import FONTES

FONTES_PARA_ENVIAR: list[tuple[str, str, str]] = [
    (m.pasta_origem, m.padrao, m.pasta_kaggle)
    for fonte in FONTES
    for m in fonte.kaggle
]


# ======================================================================
# Preparação da pasta de upload
# ======================================================================

def preparar_pasta_dataset(data_dir: Path, fontes: list[tuple[str, str, str]]) -> Path:
    """Varre `fontes` e copia os arquivos encontrados para uma pasta
    temporária de upload, preservando a separação por diretório (cada
    fonte cai na sua subpasta dentro do dataset do Kaggle)."""
    temp_folder = data_dir / "upload_tmp"
    if temp_folder.exists():
        shutil.rmtree(temp_folder)
    temp_folder.mkdir(parents=True, exist_ok=True)

    total_copiados = 0
    for idx, (pasta_origem, padrao, subpasta_kaggle) in enumerate(fontes, 1):
        origem_dir = data_dir / pasta_origem
        destino_dir = temp_folder / subpasta_kaggle
        destino_dir.mkdir(parents=True, exist_ok=True)

        arquivos = sorted(origem_dir.glob(padrao)) if origem_dir.exists() else []
        if not arquivos:
            logger.warning(f"[{idx}/{len(fontes)}] Nenhum arquivo '{padrao}' encontrado em '{origem_dir}', pulando.")
            continue

        logger.info(f"[{idx}/{len(fontes)}] {origem_dir} ({padrao}) -> {destino_dir.relative_to(temp_folder)} [{len(arquivos)} arquivo(s)]")
        for src in arquivos:
            try:
                dst = destino_dir / src.name
                shutil.copy2(src, dst)
                total_copiados += 1
            except Exception as e:
                logger.error(f"❌ Falha ao copiar '{src}': {e}")

    logger.info(f"Total de arquivos copiados: {total_copiados}")
    return temp_folder


def gerar_metadata(temp_folder: Path, dataset_id: str) -> Path:
    """Gera o dataset-metadata.json exigido pela API do Kaggle."""
    metadata_path = temp_folder / "dataset-metadata.json"
    metadata = {
        "id": dataset_id,
        "licenses": [{"name": "CC0-1.0"}],
        "resources": [],
        "version": datetime.now().strftime("%Y%m%d"),
    }
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=4)
    logger.info(f"Metadata criado em: {metadata_path}")
    return metadata_path


# ======================================================================
# Orquestração
# ======================================================================

def load_raw_to_kaggle():
    """Cria ou atualiza o dataset público no Kaggle apenas com os
    arquivos encontrados via FONTES_PARA_ENVIAR."""
    with open(KAGGLE_JSON_PATH) as f:
        kaggle_creds = json.load(f)
    dataset_id = f"{kaggle_creds['username']}/{DATASET_NAME}"

    logger.info(f"Iniciando o carregamento para o Kaggle: {dataset_id}")

    api = KaggleApi()
    api.authenticate()

    # ---------------------------------------------------------
    # FASE 1: Descobrir e copiar os arquivos para a pasta de upload
    # ---------------------------------------------------------
    temp_folder = preparar_pasta_dataset(DATA_DIR, FONTES_PARA_ENVIAR)
    gerar_metadata(temp_folder, dataset_id)

    # ---------------------------------------------------------
    # FASE 2: Criar ou atualizar o dataset no Kaggle
    # ---------------------------------------------------------
    try:
        try:
            api.dataset_list_files(dataset_id)
            dataset_existe = True
            logger.info(f"Dataset {dataset_id} já existe. Tentando atualizar...")
        except Exception as e:
            if "404 - Not Found" in str(e):
                dataset_existe = False
                logger.info(f"Dataset {dataset_id} não existe. Tentando criar...")
            else:
                raise

        if dataset_existe:
            api.dataset_create_version(
                folder=str(temp_folder),
                version_notes=f"Update {datetime.now().strftime('%Y-%m-%d')} - New version",
                delete_old_versions=True,
                dir_mode="zip",
                quiet=False,
            )
            logger.info(f"✅ Dataset {dataset_id} atualizado com sucesso!")
        else:
            api.dataset_create_new(
                folder=str(temp_folder),
                public=True,
                dir_mode="zip",
                quiet=False,
            )
            logger.info(f"✅ Dataset {dataset_id} criado com sucesso!")

    except Exception as e:
        logger.error(f"❌ Erro ao interagir com o Kaggle: {e}")
        raise
    finally:
        if temp_folder.exists():
            shutil.rmtree(temp_folder)
            logger.info(f"Pasta temporária '{temp_folder}' removida.")


if __name__ == "__main__":
    load_raw_to_kaggle()