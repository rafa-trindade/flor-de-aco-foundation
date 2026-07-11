import duckdb
from pathlib import Path

from scripts.common.paths import BASE_DIR, LANDING_DIR, PROCESSED_DIR  # noqa: F401

def query_para_csv(query: str, caminho_csv: Path, con=None):
    """
    Executa uma query no DuckDB e exporta o resultado diretamente para CSV.
    """
    fechar_conexao = False
    if con is None:
        con = duckdb.connect()
        fechar_conexao = True
        
    print(f"Processando e salvando dados em: {caminho_csv.name} ...")
    con.execute(f"""
        COPY (
            {query}
        ) TO '{caminho_csv}' (HEADER, DELIMITER ',');
    """)
    print("✔ Arquivo CSV gerado com sucesso!")
    
    if fechar_conexao:
        con.close()