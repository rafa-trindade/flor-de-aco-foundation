"""Leitura dos microdados de posição fixa da PNS/IBGE.

Cada edição tem seu próprio layout e recorte -- o módulo de violência
mudou de estrutura entre 2013 e 2019.

O arquivo é lido uma vez só; cada saída recebe os chunks já decodificados
e devolve o recorte que vai publicar.
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


def processar_pns(
    arquivo: Path,
    posicoes: dict[str, tuple[int, int]],
    nomes: dict[str, str],
    dominios: dict[str, dict],
    saidas: list[tuple[str, Callable[[pd.DataFrame], pd.DataFrame]]],
    pasta_bucket: str,
    ajuste: Callable[[pd.DataFrame], pd.DataFrame] | None = None,
) -> int:
    if not arquivo.exists():
        logger.error(f"Arquivo não encontrado: {arquivo}")
        return exit_codes.ERRO

    manifesto = carregar_manifesto(pasta_bucket)
    chave, tamanho = arquivo.name.upper(), arquivo.stat().st_size
    if manifesto.get(chave) == tamanho:
        logger.info(f"[SKIP] {arquivo.name} sem mudança desde a última execução.")
        return exit_codes.SEM_NOVIDADE

    logger.info(f"Lendo {arquivo.name} ({tamanho / 1024**2:.0f} MB)...")
    acumulado: dict[str, list] = {nome: [] for nome, _ in saidas}
    lidas = 0

    for chunk in pd.read_fwf(arquivo, colspecs=list(posicoes.values()),
                              names=list(posicoes.keys()), dtype=str,
                              chunksize=CHUNK, encoding="utf-8"):
        lidas += len(chunk)
        chunk = chunk.fillna("").apply(lambda s: s.str.strip())
        chunk = chunk.rename(columns=nomes)

        for col, mapa in dominios.items():
            if col in chunk.columns:
                chunk[col] = chunk[col].map(lambda v: mapa.get(v, v))

        if ajuste is not None:
            chunk = ajuste(chunk)

        for nome, preparar in saidas:
            parte = preparar(chunk)
            if not parte.empty:
                acumulado[nome].append(parte)

    logger.info(f"{lidas} linhas lidas.")

    for nome, partes in acumulado.items():
        df = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
        logger.info(f"{nome}: {len(df)} registros.")
        if not dataframe_para_parquet(df, pasta_bucket, nome):
            return exit_codes.ERRO

    manifesto[chave] = tamanho
    salvar_manifesto(pasta_bucket, manifesto)
    return exit_codes.SUCESSO