import pandas as pd
import duckdb
from scripts.process.mjsp.base_process_mjsp import LANDING_DIR, PROCESSED_DIR, query_para_csv

# -----------------------------------------------------------------------
# IMPORTANTE - Feminicídio vs. Homicídio Doloso (vítima mulher)
# -----------------------------------------------------------------------
# Feminicídio é qualificadora própria do homicídio doloso (Art. 121, §2º,
# VI c/c §2º-A do Código Penal, Lei 13.104/2015), condicionada a motivo de
# gênero (violência doméstica/familiar OU menosprezo/discriminação à
# condição de mulher). Mulher vítima de homicídio doloso NÃO é
# automaticamente feminicídio - é um erro comum confundir as duas coisas.
#
# Hoje (jul/2026), os recursos públicos do Sinesp/MJSP no dados.mj.gov.br
# ainda não trazem "Feminicídio" como valor de Tipo Crime (mesmo sendo um
# dos 28 indicadores oficiais do Sinesp VDE). Por isso este script gera
# DOIS arquivos:
#
#   1) feminicidio_*.csv        -> filtro EXPLÍCITO por Tipo Crime =
#      "Feminicídio". Fica vazio até o Sinesp publicar o indicador na
#      planilha, mas o código já fica pronto pra quando isso acontecer.
#
#   2) mvi_feminina_vitimas_uf_proxy.csv -> PROXY declarado: Homicídio
#      Doloso + Sexo da Vítima = Feminino. NÃO é feminicídio oficial,
#      é uma aproximação (mesma lógica de proxy já usada no
#      scripts/process/datasus/process_sim_feminicidio.py, que filtra
#      CID-10 de agressão + sexo feminino por não haver, na Declaração de
#      Óbito, um campo de "motivo de gênero").
# -----------------------------------------------------------------------

TIPO_CRIME_FEMINICIDIO = "Feminicídio"
TIPO_CRIME_HOMICIDIO_DOLOSO = "Homicídio doloso"

def main():
    landing_xlsx = LANDING_DIR / "mjsp" / "base_dados_vde.xlsx"

    if not landing_xlsx.exists():
        print("Erro: Arquivo não encontrado na Landing. Rode o extract primeiro.")
        return

    print("Lendo abas 'Ocorrências' e 'Vítimas' da Base de Dados VDE (Senasp/MJSP)...")
    # Necessário `openpyxl` no requirements.txt para o pandas ler .xlsx
    df_ocorrencias = pd.read_excel(landing_xlsx, sheet_name="Ocorrências", dtype=str)
    df_vitimas = pd.read_excel(landing_xlsx, sheet_name="Vítimas", dtype=str)

    con = duckdb.connect()
    con.register("ocorrencias", df_ocorrencias)
    con.register("vitimas", df_vitimas)

    # ---------------------------------------------------------------
    # 1) Feminicídio EXPLÍCITO (pronto para quando o Sinesp atualizar)
    # ---------------------------------------------------------------
    print(f"Filtrando Tipo Crime = '{TIPO_CRIME_FEMINICIDIO}' (explícito) na aba Ocorrências...")
    query_ocorrencias_explicito = """
        SELECT *
        FROM ocorrencias
        WHERE "Tipo Crime" ILIKE '%eminic%'
    """
    csv_ocorrencias_explicito = PROCESSED_DIR / "mjsp" / "feminicidio_ocorrencias_uf.csv"
    query_para_csv(query_ocorrencias_explicito, csv_ocorrencias_explicito, con)

    print(f"Filtrando Tipo Crime = '{TIPO_CRIME_FEMINICIDIO}' (explícito) na aba Vítimas...")
    query_vitimas_explicito = """
        SELECT *
        FROM vitimas
        WHERE "Tipo Crime" ILIKE '%eminic%'
    """
    csv_vitimas_explicito = PROCESSED_DIR / "mjsp" / "feminicidio_vitimas_uf.csv"
    query_para_csv(query_vitimas_explicito, csv_vitimas_explicito, con)

    total_explicito = con.execute(
        "SELECT COUNT(*) FROM vitimas WHERE \"Tipo Crime\" ILIKE '%eminic%'"
    ).fetchone()[0]

    if total_explicito == 0:
        print(
            "[AVISO] Nenhum registro explícito de 'Feminicídio' encontrado nesta versão "
            "da base. O Sinesp ainda não publicou esse indicador nos arquivos públicos - "
            "os CSVs acima ficarão vazios até isso mudar. Gerando o proxy declarado..."
        )

    # ---------------------------------------------------------------
    # 2) Proxy declarado: Homicídio Doloso + Sexo da Vítima = Feminino
    #    (NÃO é feminicídio oficial - ver nota no topo do arquivo)
    # ---------------------------------------------------------------
    print(
        f"Gerando proxy: Tipo Crime = '{TIPO_CRIME_HOMICIDIO_DOLOSO}' "
        "+ Sexo da Vítima = 'Feminino' na aba Vítimas..."
    )
    query_proxy = f"""
        SELECT *
        FROM vitimas
        WHERE "Tipo Crime" ILIKE '{TIPO_CRIME_HOMICIDIO_DOLOSO}'
          AND "Sexo da Vítima" ILIKE 'Feminino'
    """
    csv_proxy = PROCESSED_DIR / "mjsp" / "mvi_feminina_vitimas_uf_proxy.csv"
    query_para_csv(query_proxy, csv_proxy, con)

    con.close()

    print(
        "\nConcluído. Lembrete: 'mvi_feminina_vitimas_uf_proxy.csv' é uma APROXIMAÇÃO "
        "(homicídio doloso com vítima mulher), não o indicador oficial de feminicídio, "
        "que exige motivo de gênero comprovado (Lei 13.104/2015)."
    )

if __name__ == "__main__":
    main()