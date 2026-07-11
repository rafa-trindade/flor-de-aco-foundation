"""
Registro central de todas as fontes de dados do pipeline.

Antes desse arquivo, adicionar uma fonte nova exigia editar separadamente:
  1. scripts/extract/<fonte>/...          (o fetch em si)
  2. scripts/process/<fonte>/...          (o process em si)
  3. scripts/kaggle/load_to_kaggle.py      (FONTES_PARA_ENVIAR)
  4. docs/referencias.md e dicionario_variaveis.md (manual, fora do código)

Itens 1 e 2 continuam sendo o código de cada fonte. Este arquivo existe
para que os itens 3 (e o orquestrador run_all.py) leiam a partir de UM
registro só, em vez de listas duplicadas e que podem ficar dessincronizadas.

Para adicionar uma fonte nova:
  1. Escreva o extract/process normalmente, seguindo o padrão das
     fontes existentes (base_<fonte>.py + script(s) específico(s)).
  2. Adicione uma entrada em FONTES abaixo.
  3. Pronto -- load_to_kaggle.py e run_all.py já pegam automaticamente.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class KaggleMapping:
    """Uma pasta de `data/processed/` a ser enviada ao Kaggle."""
    pasta_origem: str   # relativo a data/, ex: "processed/mjsp"
    padrao: str          # glob, ex: "*.csv"
    pasta_kaggle: str    # subpasta de destino dentro do dataset no Kaggle


@dataclass(frozen=True)
class Fonte:
    id: str
    nome: str
    automatica: bool
    # módulos Python executáveis (têm `main()` ou rodam via `if __name__`),
    # na ordem em que devem ser chamados
    extract_modules: list[str] = field(default_factory=list)
    process_modules: list[str] = field(default_factory=list)
    kaggle: list[KaggleMapping] = field(default_factory=list)
    nota: str = ""


FONTES: list[Fonte] = [
    Fonte(
        id="macroregiao",
        nome="Macrorregião e Região de Saúde (Ministério da Saúde)",
        automatica=True,
        extract_modules=["scripts.extract.macroregiao.fetch_macroregiao_de_saude"],
        process_modules=["scripts.process.macroregiao.process_macroregiao_de_saude"],
        kaggle=[
            KaggleMapping("processed/macroregiao", "*.csv", "macroregiao"),
        ],
    ),
    Fonte(
        id="datasus_sim",
        nome="SIM/DATASUS (óbitos femininos por causas externas)",
        automatica=True,
        extract_modules=["scripts.extract.datasus.fetch_sim_causas_externas"],
        process_modules=["scripts.process.datasus.process_sim_feminicidio"],
        kaggle=[
            KaggleMapping("processed/datasus_sim", "*.csv", "datasus_sim"),
        ],
        nota=(
            "Extract via FTP -- pode falhar em VPS/cloud com a porta 21 "
            "bloqueada perto do destino (ver CHANGELOG). Nesses casos, "
            "rodar o extract localmente (Windows) e sincronizar os .dbc "
            "para data/landing/datasus/ manualmente antes do process."
        ),
    ),
    Fonte(
        id="mjsp",
        nome="Sinesp/MJSP (feminicídio explícito + proxy de MVI feminina)",
        automatica=True,
        extract_modules=["scripts.extract.mjsp.fetch_sinesp_seguranca_publica"],
        process_modules=["scripts.process.mjsp.process_sinesp_feminicidio"],
        kaggle=[
            KaggleMapping("processed/mjsp", "*.csv", "mjsp"),
        ],
        nota="feminicidio_*.csv ficam vazios até o Sinesp publicar o indicador.",
    ),
    Fonte(
        id="ibge_pns",
        nome="PNS/IBGE (mulheres vítimas de violência, 2013 e 2019)",
        automatica=False,
        process_modules=[
            "scripts.process.ibge.process_violencia_domestica_pns_2013",
            "scripts.process.ibge.process_violencia_domestica_pns_2019",
        ],
        kaggle=[
            KaggleMapping("processed/ibge", "*.csv", "ibge"),
            KaggleMapping("processed/ibge/raw", "*.txt", "ibge/raw"),
        ],
        nota="Microdados de posição fixa baixados manualmente do site do IBGE.",
    ),
    Fonte(
        id="datasen",
        nome="DataSenado (Pesquisa Violência Doméstica e Familiar, PNVD)",
        automatica=False,
        process_modules=["scripts.process.datasen.process_violencia_domestica_pnvd"],
        kaggle=[
            KaggleMapping("processed/datasen", "pnvd_violencia_dom_*.csv", "datasen"),
            KaggleMapping("processed/datasen/raw", "pnvd_*.csv", "datasen/raw"),
            KaggleMapping("processed/datasen/raw/dict", "pnvd_dict_*.xlsx", "datasen/dict"),
        ],
        nota=(
            "Sem fetch automatizado por decisão de projeto: rodadas bienais, "
            "baixo volume de atualização, e a página oficial é uma SPA sem "
            "endpoint de download estático fácil de automatizar. Baixar "
            "manualmente em https://www.senado.leg.br/institucional/datasenado/"
            "paineis_dados/#/dados-abertos e salvar em data/processed/datasen/raw/."
        ),
    ),
]


def get_fonte(id: str) -> Fonte:
    for f in FONTES:
        if f.id == id:
            return f
    raise KeyError(f"Fonte '{id}' não registrada em scripts/config/fontes.py")