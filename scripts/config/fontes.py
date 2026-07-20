"""Registro central das fontes do pipeline.

Um lugar só define, para cada fonte: os módulos de extract/process, se
tem fetch automatizado, e em qual pasta do bucket ela publica. run_all.py
e o load para o Kaggle leem daqui.

pasta_bucket é a chave do modelo streaming: é onde o Parquet final é
publicado e onde fica o _manifest.json que controla o incremental. Os
scripts de extract/process precisam usar exatamente esse mesmo valor.

Para adicionar uma fonte:
  1. Escreva o extract/process seguindo o padrão das existentes.
  2. Registre aqui.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Fonte:
    id: str
    nome: str
    pasta_bucket: str
    automatica: bool
    extract_modules: list[str] = field(default_factory=list)
    process_modules: list[str] = field(default_factory=list)
    nota: str = ""


FONTES: list[Fonte] = [
    Fonte(
        id="macroregiao",
        nome="Macrorregião e Região de Saúde (Ministério da Saúde)",
        pasta_bucket="macroregiao",
        automatica=True,
        extract_modules=["scripts.extract.macroregiao.fetch_macroregiao_de_saude"],
        process_modules=["scripts.process.macroregiao.process_macroregiao_de_saude"],
        nota="Precisa de macro_geolocalizacao.xls em MANUAL_DIR/macroregiao/.",
    ),
    Fonte(
        id="datasus_sim",
        nome="SIM/DATASUS -- óbitos femininos por agressão (CID-10 X85-Y09)",
        pasta_bucket="datasus_sim",
        automatica=True,
        extract_modules=["scripts.extract.datasus.fetch_sim_causas_externas"],
        process_modules=["scripts.process.datasus.process_sim_feminicidio"],
        nota=(
            "Extract via FTP -- pode falhar em VPS com porta 21 bloqueada. "
            "Nesse caso use SOCKS5_PROXY_ENABLED=true (ver base_ftp.py) ou "
            "rode o extract localmente."
        ),
    ),
    Fonte(
        id="mjsp",
        nome="Sinesp/MJSP -- feminicídio explícito e MVI feminina",
        pasta_bucket="mjsp",
        automatica=True,
        extract_modules=["scripts.extract.mjsp.fetch_sinesp_seguranca_publica"],
        process_modules=["scripts.process.mjsp.process_sinesp_feminicidio"],
        nota="Indicador de feminicídio fica vazio até o Sinesp publicá-lo.",
    ),
    Fonte(
        id="ibge_pns",
        nome="PNS/IBGE -- mulheres vítimas de violência (2013 e 2019)",
        pasta_bucket="ibge",
        automatica=False,
        process_modules=[
            "scripts.process.ibge.process_violencia_domestica_pns_2013",
            "scripts.process.ibge.process_violencia_domestica_pns_2019",
        ],
        nota="Microdados de posição fixa em MANUAL_DIR/ibge/pns/ (PNS_2013.txt, PNS_2019.txt).",
    ),
    Fonte(
        id="datasen",
        nome="DataSenado -- Pesquisa Violência Doméstica e Familiar (PNVD)",
        pasta_bucket="datasen",
        automatica=False,
        process_modules=["scripts.process.datasen.process_violencia_domestica_pnvd"],
        nota=(
            "Sem fetch automatizado: rodadas bienais e a página oficial é SPA "
            "sem endpoint estático. Baixar de senado.leg.br/institucional/"
            "datasenado/paineis_dados/#/dados-abertos para MANUAL_DIR/datasen/."
        ),
    ),
]


def get_fonte(id: str) -> Fonte:
    for f in FONTES:
        if f.id == id:
            return f
    raise KeyError(f"Fonte '{id}' não registrada em scripts/config/fontes.py")


def pastas_bucket() -> list[str]:
    """Pastas distintas do bucket, na ordem de registro."""
    vistas = []
    for f in FONTES:
        if f.pasta_bucket not in vistas:
            vistas.append(f.pasta_bucket)
    return vistas