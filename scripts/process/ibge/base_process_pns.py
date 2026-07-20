"""Leitura dos microdados de posição fixa da PNS/IBGE.

Cada edição tem seu próprio layout (posições, nomes e domínios) e seu
próprio filtro -- o questionário de violência mudou entre 2013 e 2019.
"""
import logging
from pathlib import Path
from typing import Callable

import pandas as pd

from scripts.common import exit_codes
from scripts.common.bucket_sync import carregar_manifesto, salvar_manifesto
from scripts.common.publish import dataframe_para_parquet

logger = logging.getLogger(__name__)

CHUNK = 200_000


def _aplicar_dominios(df: pd.DataFrame, mapeamentos: dict) -> pd.DataFrame:
    for col, mapa in mapeamentos.items():
        if col in df.columns:
            df[col] = df[col].map(lambda v: mapa.get(v, v))
    return df


def processar_pns(
    arquivo: Path,
    posicoes: dict[str, tuple[int, int]],
    nomes: dict[str, str],
    mapeamentos: dict[str, dict],
    filtro: Callable[[pd.DataFrame], pd.DataFrame],
    pasta_bucket: str,
    nome_saida: str,
    ajuste: Callable[[pd.DataFrame], pd.DataFrame] | None = None,
) -> int:
    if not arquivo.exists():
        logger.error(f"Arquivo não encontrado: {arquivo}")
        return exit_codes.ERRO

    manifesto = carregar_manifesto(pasta_bucket)
    chave = arquivo.name.upper()
    tamanho = arquivo.stat().st_size
    if manifesto.get(chave) == tamanho:
        logger.info(f"[SKIP] {arquivo.name} sem mudança desde a última execução.")
        return exit_codes.SEM_NOVIDADE

    colspecs = list(posicoes.values())
    colunas = list(posicoes.keys())

    logger.info(f"Lendo {arquivo.name} ({tamanho / 1024**2:.0f} MB)...")
    partes = []
    lidas = 0
    for chunk in pd.read_fwf(arquivo, colspecs=colspecs, names=colunas,
                              dtype=str, chunksize=CHUNK, encoding="utf-8"):
        lidas += len(chunk)
        chunk = chunk.fillna("").apply(lambda s: s.str.strip())
        chunk = _aplicar_dominios(chunk, mapeamentos)
        chunk = chunk.rename(columns=nomes)
        if ajuste is not None:
            chunk = ajuste(chunk)
        chunk = filtro(chunk)
        if not chunk.empty:
            partes.append(chunk)

    logger.info(f"{lidas} linhas lidas.")
    df = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=list(nomes.values()))
    logger.info(f"{len(df)} registros após o filtro.")

    if not dataframe_para_parquet(df, pasta_bucket, nome_saida):
        return exit_codes.ERRO

    manifesto[chave] = tamanho
    salvar_manifesto(pasta_bucket, manifesto)
    return exit_codes.SUCESSO