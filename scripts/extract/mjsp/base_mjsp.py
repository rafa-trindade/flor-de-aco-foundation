import requests
import zipfile
from io import BytesIO
from pathlib import Path

from scripts.common.paths import BASE_DIR, LANDING_DIR, PROCESSED_DIR  # noqa: F401

# -----------------------------------------
# Funções Utilitárias Reutilizáveis
# -----------------------------------------
EXTENSOES_PLANILHA = (".xlsx", ".xls", ".csv")

def baixar_e_extrair_planilha(url: str, caminho_destino: Path):
    """
    Baixa um arquivo ZIP da URL, extrai a primeira planilha encontrada
    (.xlsx, .xls ou .csv, nessa ordem de prioridade) e salva no caminho
    de destino (Landing Zone). Usado para a Base de Dados VDE, que não
    tem formato fixo garantido dentro do .zip.
    """
    caminho_destino.parent.mkdir(parents=True, exist_ok=True)

    print(f"Baixando: {url}")
    response = requests.get(url, timeout=120)
    response.raise_for_status()

    print("Descompactando o arquivo ZIP...")
    with zipfile.ZipFile(BytesIO(response.content)) as z:
        candidatos = [n for n in z.namelist() if n.lower().endswith(EXTENSOES_PLANILHA)]
        if not candidatos:
            raise FileNotFoundError(
                f"Nenhuma planilha ({', '.join(EXTENSOES_PLANILHA)}) encontrada no ZIP. "
                f"Conteúdo do ZIP: {z.namelist()}"
            )

        # Prioriza xlsx > xls > csv, caso existam múltiplos arquivos
        for ext in EXTENSOES_PLANILHA:
            achou = next((n for n in candidatos if n.lower().endswith(ext)), None)
            if achou:
                nome_arquivo = achou
                break

        destino_final = caminho_destino.with_suffix(Path(nome_arquivo).suffix)
        with z.open(nome_arquivo) as arquivo_zip:
            with open(destino_final, "wb") as f_out:
                f_out.write(arquivo_zip.read())

    print(f"✔ Arquivo salvo em Landing: {destino_final.name}")
    return destino_final

def baixar_arquivo(url: str, caminho_destino: Path):
    """
    Baixa um arquivo diretamente da URL (XLSX, CSV, PDF, etc.) e salva
    no caminho de destino (Landing Zone), sem descompactação.
    Usado para fontes que disponibilizam o recurso já "solto" (sem .zip),
    como os datasets do Portal de Dados Abertos do MJSP.
    """
    caminho_destino.parent.mkdir(parents=True, exist_ok=True)

    print(f"Baixando: {url}")
    response = requests.get(url, timeout=60)
    response.raise_for_status()

    with open(caminho_destino, "wb") as f_out:
        f_out.write(response.content)

    print(f"✔ Arquivo salvo em Landing: {caminho_destino.name}")