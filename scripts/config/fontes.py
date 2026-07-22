"""Catálogo de fontes e módulos do pipeline.
Nota: `pasta_bucket` define o destino obrigatório do Parquet e do _manifest.json.
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
        nota="Dependência manual: requer o arquivo `macro_geolocalizacao.xls` salvo no diretório env `FLOR_DE_ACO_MANUAL_DIR`.",
    ),
    Fonte(
        id="datasus_sim",
        nome="SIM/DATASUS -- óbitos femininos por agressão (CID-10 X85-Y09)",
        pasta_bucket="datasus_sim",
        automatica=True,
        extract_modules=["scripts.extract.datasus.fetch_sim_causas_externas"],
        process_modules=["scripts.process.datasus.process_proxy_sim_feminicidio"],
        nota=(
            "A extração via FTP pode falhar em servidores VPS com a porta 21 bloqueada. "
            "Nesses casos, ative `SOCKS5_PROXY_ENABLED=true` (consulte `base_ftp.py`) "
            "ou execute o módulo de extração localmente."
        ),
    ),
    Fonte(
        id="datasus_sinan",
        nome="SINAN/DATASUS -- violência interpessoal contra mulheres (ficha VIOL)",
        pasta_bucket="datasus_sinan",
        automatica=True,
        extract_modules=["scripts.extract.datasus.fetch_sinan_violencia"],
        process_modules=["scripts.process.datasus.process_sinan_violencia"],
        nota=(
            "Contexto: registra violência não fatal notificada em serviços de saúde, "
            "incluindo a relação vítima-agressor (dado ausente na Declaração de Óbito do SIM). "
            "Recorte aplicado: sexo feminino, excluindo lesões autoprovocadas. "
            "Atenção: aplicam-se as mesmas ressalvas de FTP da fonte `datasus_sim`."
        ),
    ),
    Fonte(
        id="datajud",
        nome="CNJ/Datajud -- processos de violência contra a mulher",
        pasta_bucket="datajud",
        automatica=True,
        extract_modules=["scripts.extract.datajud.fetch_datajud_violencia"],
        process_modules=["scripts.process.datajud.process_datajud_violencia"],
        nota=(
            "Contexto: contém apenas metadados processuais e mede a judicialização, "
            "não o perfil das vítimas (a API não expõe as partes). "
            "Técnico: a API é instável e o download leva horas, por isso há checkpoint no bucket. "
            "O NDJSON bruto é salvo em env `FLOR_DE_ACO_MANUAL_DIR/datajud/`. "
            "Recortes via argumento: `feminicidio`, `violencia_genero` ou `contexto_domestico`."
        ),
    ),
    Fonte(
        id="ibge_pns",
        nome="PNS/IBGE -- mulheres vítimas de violência (2013 e 2019)",
        pasta_bucket="ibge",
        automatica=False,
        process_modules=[
            "scripts.process.ibge.process_pns_violencia_2013",
            "scripts.process.ibge.process_pns_violencia_domestica_2019",
        ],
        nota=(
            "Dependência manual: microdados de posição fixa devem estar em env `FLOR_DE_ACO_MANUAL_DIR/ibge/pns/`. "
            "A edição de 2013 possui duas bases separadas (violência por pessoa conhecida e por desconhecida). "
            "A edição de 2019 unifica os dados, detalhando o agressor por tipo de violência."
        ),
    ),
    Fonte(
        id="datasen",
        nome="DataSenado -- Pesquisa Violência Doméstica e Familiar (PNVD)",
        pasta_bucket="datasen",
        automatica=False,
        process_modules=["scripts.process.datasen.process_pn_violencia_domestica"],
        nota=(
            "Sem extração automatizada (página em SPA sem endpoint estático). "
            "O download das rodadas bienais deve ser feito manualmente no portal de Dados Abertos "
            "(senado.leg.br/institucional/datasenado/paineis_dados/#/dados-abertos) "
            "e os arquivos salvos em env `FLOR_DE_ACO_MANUAL_DIR/datasen/`."
        ),
    ),
]


def get_fonte(id: str) -> Fonte:
    for f in FONTES:
        if f.id == id:
            return f
    raise KeyError(f"Fonte '{id}' não registrada em scripts/config/fontes.py")


def pastas_bucket() -> list[str]:
    vistas = []
    for f in FONTES:
        if f.pasta_bucket not in vistas:
            vistas.append(f.pasta_bucket)
    return vistas