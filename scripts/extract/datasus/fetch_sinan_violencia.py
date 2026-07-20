"""SINAN -- Violência Interpessoal/Autoprovocada (ficha VIOL).

Notificação compulsória de violência atendida em serviço de saúde.
Diferente do SIM, registra casos NÃO fatais -- e traz relação da vítima
com o agressor, o que o atestado de óbito não tem.

Arquivos são nacionais (VIOLBR{AA}.dbc), não por UF.
"""
import sys

from scripts.extract.datasus.base_ftp import sincronizar_ftp
from scripts.common.paths import LANDING_DIR
from scripts.common import exit_codes

OUTPUT_DIR = str(LANDING_DIR / "datasus" / "dbc_sinan_violencia")
PASTA_BUCKET = "datasus_sinan"

PREFIXO = "VIOLBR"

FONTES_FTP = [
    ("/dissemin/publicos/SINAN/DADOS/FINAIS", "Consolidados"),
    ("/dissemin/publicos/SINAN/DADOS/PRELIM", "Preliminares"),
]


def regra(nome_arquivo: str) -> bool:
    nome = nome_arquivo.upper()
    if not (nome.startswith(PREFIXO) and nome.endswith(".DBC")):
        return False
    return nome[len(PREFIXO):-4].isdigit()


if __name__ == "__main__":
    sucesso_geral = True
    houve_novidade = False

    for diretorio, tipo in FONTES_FTP:
        print(f"Sincronizando dados {tipo} do diretório: {diretorio}")
        sucesso, novidade = sincronizar_ftp(
            diretorio, OUTPUT_DIR, regra, pasta_bucket=PASTA_BUCKET
        )
        sucesso_geral = sucesso_geral and sucesso
        houve_novidade = houve_novidade or novidade

    if not sucesso_geral:
        sys.exit(exit_codes.ERRO)
    if not houve_novidade:
        print("[INFO] Nenhum arquivo novo desde a última execução.")
        sys.exit(exit_codes.SEM_NOVIDADE)
    sys.exit(exit_codes.SUCESSO)