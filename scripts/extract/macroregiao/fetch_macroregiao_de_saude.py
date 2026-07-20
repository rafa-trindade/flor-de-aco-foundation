"""Macrorregião de Saúde -- CSV de municípios (Dados Abertos MS)."""
import random
import sys
import time
import zipfile
from io import BytesIO

import requests

from scripts.common.paths import LANDING_DIR
from scripts.common import exit_codes
from scripts.common.bucket_sync import carregar_manifesto, salvar_manifesto

URL = "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/dbgeral/macroregiao_de_saude_csv.zip"
PASTA_BUCKET = "macroregiao"
CHAVE_MANIFESTO = "macroregiao_de_saude_csv.zip"
CSV_DIR = LANDING_DIR / "macroregiao"
CSV_LOCAL = CSV_DIR / "macroregiao.csv"

# O CKAN da Saúde rejeita o User-Agent padrão do requests e devolve 503
# intermitente sob carga.
CABECALHOS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0"}
MAX_TENTATIVAS = 4


def _tamanho_remoto() -> int | None:
    try:
        r = requests.head(URL, headers=CABECALHOS, timeout=30, allow_redirects=True)
        r.raise_for_status()
        return int(r.headers.get("Content-Length", 0)) or None
    except requests.RequestException as e:
        print(f"[AVISO] Não consegui consultar o tamanho remoto: {e}")
        return None


def _baixar() -> bytes | None:
    for tentativa in range(MAX_TENTATIVAS):
        try:
            print(f"Baixando ({tentativa + 1}/{MAX_TENTATIVAS}): {URL}")
            r = requests.get(URL, headers=CABECALHOS, timeout=120)
            r.raise_for_status()
            return r.content
        except requests.RequestException as e:
            print(f"[AVISO] Tentativa {tentativa + 1} falhou: {e}")
            if tentativa < MAX_TENTATIVAS - 1:
                time.sleep(min(3 * (2 ** tentativa), 60) + random.uniform(0, 2))
    print(f"[ERRO] Falhou após {MAX_TENTATIVAS} tentativas.")
    return None


def main() -> int:
    manifesto = carregar_manifesto(PASTA_BUCKET)
    tamanho_remoto = _tamanho_remoto()

    if tamanho_remoto and manifesto.get(CHAVE_MANIFESTO.upper()) == tamanho_remoto:
        print("[SKIP] Sem mudança desde a última execução.")
        return exit_codes.SEM_NOVIDADE

    conteudo = _baixar()
    if conteudo is None:
        return exit_codes.ERRO

    CSV_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(BytesIO(conteudo)) as z:
            nomes = [n for n in z.namelist() if n.lower().endswith(".csv")]
            if not nomes:
                print("[ERRO] Nenhum .csv dentro do ZIP.")
                return exit_codes.ERRO
            with z.open(nomes[0]) as origem, open(CSV_LOCAL, "wb") as destino:
                destino.write(origem.read())
    except zipfile.BadZipFile as e:
        print(f"[ERRO] ZIP inválido: {e}")
        return exit_codes.ERRO

    print(f"✔ Salvo em landing: {CSV_LOCAL.name}")

    # Só depois do download completo: gravar antes marcaria como
    # incorporado algo que o process ainda não viu.
    if tamanho_remoto:
        manifesto[CHAVE_MANIFESTO.upper()] = tamanho_remoto
        salvar_manifesto(PASTA_BUCKET, manifesto)

    return exit_codes.SUCESSO


if __name__ == "__main__":
    sys.exit(main())