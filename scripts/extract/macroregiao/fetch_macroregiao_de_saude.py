from scripts.extract.macroregiao.base_macroregiao import LANDING_DIR, baixar_e_extrair_csv

CSV_DIR = LANDING_DIR / "macroregiao"

def main():
    url = "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/dbgeral/macroregiao_de_saude_csv.zip"
    landing_file = CSV_DIR / "macroregiao.csv"
    
    baixar_e_extrair_csv(url, landing_file)
    print("Lembre-se de garantir que o arquivo 'macro_geolocalizacao.xls' está na pasta Landing.")

if __name__ == "__main__":
    main()