"""
Sinesp/MJSP - Dados Nacionais de Segurança Pública

Baixa a planilha oficial de indicadores de segurança pública por Unidade
da Federação (UF), publicada pela Secretaria Nacional de Segurança Pública
(Senasp/MJSP) no Portal de Dados Abertos do Ministério da Justiça e
Segurança Pública (dados.mj.gov.br).

Fonte: https://dados.mj.gov.br/dataset/sistema-nacional-de-estatisticas-de-seguranca-publica

Contém os 28 indicadores nacionais definidos pela Resolução n. 06
ConSinesp/MJSP e pela Portaria nº 229/2018 (Sinesp VDE), entre eles o
indicador "feminicídio", com abrangência nacional (série por UF/ano).
"""
from scripts.extract.mjsp.base_mjsp import LANDING_DIR, baixar_arquivo

XLSX_DIR = LANDING_DIR / "mjsp"

def main():
    url = (
        "https://dados.mj.gov.br/dataset/210b9ae2-21fc-4986-89c6-2006eb4db247"
        "/resource/feeae05e-faba-406c-8a4a-512aec91a9d1"
        "/download/indicadoressegurancapublicauf.xlsx"
    )
    landing_file = XLSX_DIR / "base_dados_vde.xlsx"

    baixar_arquivo(url, landing_file)
    print("Lembre-se de rodar o process para filtrar apenas o indicador 'feminicídio'.")

if __name__ == "__main__":
    main()