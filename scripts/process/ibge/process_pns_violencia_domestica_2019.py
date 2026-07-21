"""Mapeamento posicional PNS/IBGE 2019 (Bloco V - Violência).

Mudança de schema (vs 2013): Agrupamento unificado por tipo de ato (psicológica, física, sexual), com o agressor mapeado como coluna.
Regra de negócio: Inclui dados de série histórica estendida para violência sexual ("alguma vez na vida").
"""
import sys

import pandas as pd

from scripts.common.paths import MANUAL_PNS_DIR
from scripts.process.ibge.base_process_pns import processar_pns

PASTA_BUCKET = "ibge"
ARQUIVO = MANUAL_PNS_DIR / "PNS_2019.txt"
SAIDA = "pns_violencia_domestica_2019.parquet"

COLUNAS_VIOLENCIA = [
    "psi_humilhacao_publica", "psi_gritos", "psi_ameaca_digital",
    "psi_ameaca_terceiro", "psi_destruiu_bem",
    "fis_tapa", "fis_empurrao", "fis_soco_chute", "fis_estrangulamento", "fis_arma",
    "sex_toque_forcado_12m", "sex_relacao_forcada_12m",
    "sex_toque_forcado_vida", "sex_relacao_forcada_vida",
]

COLUNAS_AGRESSOR = ["psi_agressor", "fis_agressor", "sex_agressor"]

AGRESSOR_PARCEIRO_INTIMO = {
    "Cônjuge ou companheiro (a)",
    "Ex-Cônjuge ou ex-companheiro (a)",
    "Parceiro (a), namorado (a), ex-parceiro (a), ex-namorado (a)",
    "Parceiro (a), namorado (a), ex-parceiro (a), ex-namorado (a",
}

POSICOES = {
    'V0001': (0, 2),
    'V0024': (2, 9),
    'UPA_PNS': (9, 18),
    'V0006_PNS': (18, 22),
    'V0026': (30, 31),
    'C006': (107, 108),
    'C008': (116, 119),
    'C009': (119, 120),
    'V001': (1245, 1246),
    'V00201': (1247, 1248),
    'V00202': (1248, 1249),
    'V00203': (1249, 1250),
    'V00204': (1250, 1251),
    'V00205': (1251, 1252),
    'V003': (1252, 1253),
    'V006': (1253, 1255),
    'V007': (1255, 1256),
    'V01401': (1256, 1257),
    'V01402': (1257, 1258),
    'V01403': (1258, 1259),
    'V01404': (1259, 1260),
    'V01405': (1260, 1261),
    'V015': (1261, 1262),
    'V018': (1262, 1264),
    'V019': (1264, 1265),
    'V02701': (1265, 1266),
    'V02702': (1266, 1267),
    'V02801': (1267, 1268),
    'V02802': (1268, 1269),
    'V029': (1269, 1270),
    'V032': (1270, 1272),
    'V033': (1272, 1273),
    'V034': (1273, 1274),
    'V00291': (1425, 1439),
}

NOMES = {
    'V0001': 'uf',
    'V0024': 'estrato',
    'UPA_PNS': 'upa',
    'V0006_PNS': 'domicilio',
    'V0026': 'situacao_censitaria',
    'C006': 'sexo',
    'C008': 'idade',
    'C009': 'raca_cor',
    'V00291': 'peso_amostral',
    'V001': 'privacidade_assegurada',
    'V00201': 'psi_humilhacao_publica',
    'V00202': 'psi_gritos',
    'V00203': 'psi_ameaca_digital',
    'V00204': 'psi_ameaca_terceiro',
    'V00205': 'psi_destruiu_bem',
    'V003': 'psi_frequencia',
    'V006': 'psi_agressor',
    'V007': 'psi_local',
    'V01401': 'fis_tapa',
    'V01402': 'fis_empurrao',
    'V01403': 'fis_soco_chute',
    'V01404': 'fis_estrangulamento',
    'V01405': 'fis_arma',
    'V015': 'fis_frequencia',
    'V018': 'fis_agressor',
    'V019': 'fis_local',
    'V02701': 'sex_toque_forcado_12m',
    'V02702': 'sex_relacao_forcada_12m',
    'V02801': 'sex_toque_forcado_vida',
    'V02802': 'sex_relacao_forcada_vida',
    'V029': 'sex_frequencia',
    'V032': 'sex_agressor',
    'V033': 'sex_local',
    'V034': 'deixou_atividades',
}

DOMINIOS = {
    'uf': {
        '11': 'Rondônia',
        '12': 'Acre',
        '13': 'Amazonas',
        '14': 'Roraima',
        '15': 'Pará',
        '16': 'Amapá',
        '17': 'Tocantins',
        '21': 'Maranhão',
        '22': 'Piauí',
        '23': 'Ceará',
        '24': 'Rio Grande do Norte',
        '25': 'Paraíba',
        '26': 'Pernambuco',
        '27': 'Alagoas',
        '28': 'Sergipe',
        '29': 'Bahia',
        '31': 'Minas Gerais',
        '32': 'Espírito Santo',
        '33': 'Rio de Janeiro',
        '35': 'São Paulo',
        '41': 'Paraná',
        '42': 'Santa Catarina',
        '43': 'Rio Grande do Sul',
        '50': 'Mato Grosso do Sul',
        '51': 'Mato Grosso',
        '52': 'Goiás',
        '53': 'Distrito Federal',
    },
    'situacao_censitaria': {
        '1': 'Urbano',
        '2': 'Rural',
    },
    'sexo': {
        '1': 'Homem',
        '2': 'Mulher',
    },
    'idade': {
        '000 a 130': 'Idade (em anos)',
    },
    'raca_cor': {
        '1': 'Branca',
        '2': 'Preta',
        '3': 'Amarela',
        '4': 'Parda',
        '5': 'Indígena',
        '9': 'Ignorado',
    },
    'privacidade_assegurada': {
        '1': 'Sim',
        '2': 'Não',
    },
    'psi_humilhacao_publica': {
        '1': 'Sim',
        '2': 'Não',
    },
    'psi_gritos': {
        '1': 'Sim',
        '2': 'Não',
    },
    'psi_ameaca_digital': {
        '1': 'Sim',
        '2': 'Não',
    },
    'psi_ameaca_terceiro': {
        '1': 'Sim',
        '2': 'Não',
    },
    'psi_destruiu_bem': {
        '1': 'Sim',
        '2': 'Não',
    },
    'psi_frequencia': {
        '1': 'Muitas vezes',
        '2': 'Algumas vezes',
        '3': 'Uma vez',
    },
    'psi_agressor': {
        '01': 'Cônjuge ou companheiro (a)',
        '02': 'Ex-Cônjuge ou ex-companheiro (a)',
        '03': 'Parceiro (a), namorado (a), ex-parceiro (a), ex-namorado (a)',
        '04': 'Pai, mãe, padrasto ou madrasta',
        '05': 'Filho(a), enteado(a)',
        '06': 'Irmão(ã)',
        '07': 'Outro parente',
        '08': 'Amigo(a)/colega, vizinho(a)',
        '09': 'Empregado (a) em geral',
        '10': 'Patrão/patroa/chefe',
        '11': 'Pessoa desconhecida',
        '12': 'Policial',
        '13': 'Outro',
    },
    'psi_local': {
        '1': 'Residência',
        '2': 'Trabalho',
        '3': 'Escola, faculdade ou outro estabelecimento de ensino',
        '4': 'Bar, restaurante ou similar',
        '5': 'Via pública ou outro local público',
        '6': 'Internet/Redes Sociais/Celular',
        '7': 'Outro',
    },
    'fis_tapa': {
        '1': 'Sim',
        '2': 'Não',
    },
    'fis_empurrao': {
        '1': 'Sim',
        '2': 'Não',
    },
    'fis_soco_chute': {
        '1': 'Sim',
        '2': 'Não',
    },
    'fis_estrangulamento': {
        '1': 'Sim',
        '2': 'Não',
    },
    'fis_arma': {
        '1': 'Sim',
        '2': 'Não',
    },
    'fis_frequencia': {
        '1': 'Muitas vezes',
        '2': 'Algumas vezes',
        '3': 'Uma vez',
    },
    'fis_agressor': {
        '01': 'Cônjuge ou companheiro (a)',
        '02': 'Ex-Cônjuge ou ex-companheiro (a)',
        '03': 'Parceiro (a), namorado (a), ex-parceiro (a), ex-namorado (a',
        '04': 'Pai, mãe, padrasto ou madrasta',
        '05': 'Filho(a), enteado(a',
        '06': 'Irmão(ã)',
        '07': 'Outro parente',
        '08': 'Amigo(a)/colega, vizinho(a)',
        '09': 'Empregado (a) em geral',
        '10': 'Patrão/patroa/chefe(a)',
        '11': 'Pessoa desconhecida',
        '12': 'Policial',
        '13': 'Outro',
    },
    'fis_local': {
        '1': 'Residência',
        '2': 'Trabalho',
        '3': 'Escola, faculdade ou outro estabelecimento de ensino',
        '4': 'Bar, restaurante ou similar',
        '5': 'Via pública ou outro local público',
        '6': 'Outro',
    },
    'sex_toque_forcado_12m': {
        '1': 'Sim',
        '2': 'Não',
    },
    'sex_relacao_forcada_12m': {
        '1': 'Sim',
        '2': 'Não',
    },
    'sex_toque_forcado_vida': {
        '1': 'Sim',
        '2': 'Não',
    },
    'sex_relacao_forcada_vida': {
        '1': 'Sim',
        '2': 'Não',
    },
    'sex_frequencia': {
        '1': 'Muitas vezes',
        '2': 'Algumas vezes',
        '3': 'Uma vez',
    },
    'sex_agressor': {
        '01': 'Cônjuge ou companheiro (a)',
        '02': 'Ex-Cônjuge ou ex-companheiro (a',
        '03': 'Parceiro (a), namorado (a), ex-parceiro (a), ex-namorado (a)',
        '04': 'Pai, mãe, padrasto ou madrasta',
        '05': 'Filho(a), enteado(a)',
        '06': 'Irmão(ã)',
        '07': 'Outro parente',
        '08': 'Amigo(a)/colega, vizinho(a',
        '09': 'Empregado (a) em geral',
        '10': 'Patrão/patroa/chefe',
        '11': 'Pessoa desconhecida',
        '12': 'Policial',
        '13': 'Outro',
    },
    'sex_local': {
        '1': 'Residência',
        '2': 'Trabalho',
        '3': 'Escola, faculdade ou outro estabelecimento de ensino',
        '4': 'Bar, restaurante ou similar',
        '5': 'Via pública ou outro local público',
        '6': 'Outro',
    },
    'deixou_atividades': {
        '1': 'Sim',
        '2': 'Não',
    },
    'peso_amostral': {
        '5 dígitos e 8 casas decimais': 'Peso do morador selecionado com correção de não entrevista com calibração pela projeção de população para morador selecionado - Usado no cálculo de indicadores de morador selecionado',
    },
}


def ajuste(df):
    """Correção de zero-fill em layout posicional (idade e peso amostral)."""
    df["idade"] = df["idade"].str.lstrip("0").replace("", "0")
    df["peso_amostral"] = pd.to_numeric(df["peso_amostral"], errors="coerce") / 10**8
    return df


def preparar(df):
    # Fix de domínio: IBGE alterou a flag de 'Feminino' (2013) para 'Mulher' (2019).
    r = df[df["sexo"] == "Mulher"]
    r = r[r[COLUNAS_VIOLENCIA].eq("Sim").any(axis=1)]
    if r.empty:
        return r
    r = r.copy()
    r["parceiro_intimo"] = r[COLUNAS_AGRESSOR].isin(AGRESSOR_PARCEIRO_INTIMO).any(axis=1)
    return r


if __name__ == "__main__":
    sys.exit(processar_pns(
        arquivo=ARQUIVO,
        posicoes=POSICOES,
        nomes=NOMES,
        dominios=DOMINIOS,
        saidas=[(SAIDA, preparar)],
        pasta_bucket=PASTA_BUCKET,
        ajuste=ajuste,
    ))