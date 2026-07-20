"""PNS/IBGE 2013 -- módulo de violência (bloco O).

Posições, nomes e domínios extraídos do dicionário oficial
(dicionario_pns_microdados_2013.xls).

O questionário separa dois blocos:
  O025-O036  violência por pessoa DESCONHECIDA (bandido, policial, assaltante)
  O037-O048  violência por pessoa CONHECIDA (cônjuge, parente, amigo, vizinho)

Só o segundo é violência doméstica/familiar. Publica os dois em arquivos
distintos: misturá-los descaracteriza o recorte do projeto.

Microdados de posição fixa em MANUAL_DIR (ver env.example).
"""
import sys

import pandas as pd

from scripts.common.paths import MANUAL_PNS_DIR
from scripts.process.ibge.base_process_pns import processar_pns

PASTA_BUCKET = "ibge"
ARQUIVO = MANUAL_PNS_DIR / "PNS_2013.txt"

SAIDA_CONHECIDO = "pns_violencia_domestica_2013.parquet"
SAIDA_DESCONHECIDO = "pns_proxy_violencia_desconhecido_2013.parquet"

# O042: agressor na violência por pessoa conhecida
AGRESSOR_PARCEIRO_INTIMO = {
    "Cônjuge, companheiro(a), namorado(a)",
    "Ex-cônjuge, ex-companheiro(a), ex-namorado(a)",
}

COLUNAS_COMUNS = ["uf", "estrato", "upa", "domicilio", "situacao_censitaria",
                  "sexo", "idade", "raca_cor", "peso_amostral"]

POSICOES = {
    'V0001': (0, 2),
    'V0024': (2, 9),
    'UPA_PNS': (9, 16),
    'V0006_PNS': (16, 20),
    'V0026': (37, 38),
    'C006': (105, 106),
    'C008': (114, 117),
    'C009': (117, 118),
    'O025': (606, 607),
    'O027': (607, 608),
    'O028': (608, 609),
    'O029': (609, 610),
    'O030': (610, 611),
    'O031': (611, 612),
    'O032': (612, 613),
    'O033': (613, 614),
    'O034': (614, 616),
    'O035': (616, 617),
    'O036': (617, 618),
    'O037': (618, 619),
    'O038': (619, 620),
    'O039': (620, 621),
    'O040': (621, 622),
    'O041': (622, 623),
    'O042': (623, 625),
    'O043': (625, 626),
    'O044': (626, 627),
    'O045': (627, 628),
    'O046': (628, 630),
    'O047': (630, 631),
    'O048': (631, 632),
    'V00291': (1404, 1418),
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
    'O037': 'sofreu_violencia',
    'O038': 'frequencia_violencia',
    'O039': 'tipo_violencia',
    'O040': 'meio_agressao',
    'O041': 'local_ocorrencia',
    'O042': 'agressor',
    'O043': 'deixou_atividades',
    'O044': 'teve_lesao',
    'O045': 'buscou_saude',
    'O046': 'local_atendimento',
    'O047': 'internacao_24h',
    'O048': 'teve_sequela',
    'O025': 'd_sofreu_violencia',
    'O027': 'd_tipo_violencia',
    'O028': 'd_meio_agressao',
    'O029': 'd_local_ocorrencia',
    'O030': 'd_agressor',
    'O031': 'd_deixou_atividades',
    'O032': 'd_teve_lesao',
    'O033': 'd_buscou_saude',
    'O034': 'd_local_atendimento',
    'O035': 'd_internacao_24h',
    'O036': 'd_teve_sequela',
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
        '1': 'Masculino',
        '2': 'Feminino',
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
    'd_sofreu_violencia': {
        '1': 'Sim',
        '2': 'Não',
    },
    'd_tipo_violencia': {
        '1': 'Física',
        '2': 'Sexual',
        '3': 'Psicológica',
        '4': 'Outro',
    },
    'd_meio_agressao': {
        '1': 'Com arma de fogo (revólver, escopeta, pistola)',
        '2': 'Com objeto pérfuro-cortante (faca, navalha, punhal, tesoura)',
        '3': 'Com objeto contundente (pau, cassetete, barra de ferro, pedra)',
        '4': 'Com força corporal, espancamento (tapa, murro, empurrão)',
        '5': 'Por meio de palavras ofensivas, xingamentos ou palavrões',
        '6': 'Outro',
    },
    'd_local_ocorrencia': {
        '1': 'Residência',
        '2': 'Trabalho',
        '3': 'Escola/Faculdade ou similar',
        '4': 'Bar ou similar',
        '5': 'Via pública',
        '6': 'Banco/Caixa eletrônico/Lotérica',
        '7': 'Outro',
    },
    'd_agressor': {
        '1': 'Bandido, ladrão ou assaltante',
        '2': 'Agente legal público (policial/agente da lei)',
        '3': 'Outro',
    },
    'd_deixou_atividades': {
        '1': 'Sim',
        '2': 'Não',
    },
    'd_teve_lesao': {
        '1': 'Sim',
        '2': 'Não',
    },
    'd_buscou_saude': {
        '1': 'Sim',
        '2': 'Não',
    },
    'd_local_atendimento': {
        '01': 'No local da violência',
        '02': 'Unidade básica de saúde (posto ou centro de saúde ou unidade de saúde da família)',
        '03': 'Centro de Especialidades, Policlínica pública ou PAM Posto de Assistência Médica',
        '04': 'UPA (Unidade de Pronto Atendimento)',
        '05': 'Outro tipo de Pronto Atendimento Público (24 horas)',
        '06': 'Pronto-socorro ou emergência de hospital público',
        '07': 'Hospital público/ambulatório',
        '08': 'Consultório particular ou Clínica privada',
        '09': 'Ambulatório ou consultório de empresa ou sindicato',
        '10': 'Pronto-atendimento ou emergência de hospital privado',
        '11': 'No domicílio, com médico particular',
        '12': 'No domicílio, com médico da equipe de saúde da família',
        '13': 'Outro',
    },
    'd_internacao_24h': {
        '1': 'Sim',
        '2': 'Não',
    },
    'd_teve_sequela': {
        '1': 'Sim',
        '2': 'Não',
    },
    'sofreu_violencia': {
        '1': 'Sim',
        '2': 'Não',
    },
    'frequencia_violencia': {
        '1': 'Uma vez',
        '2': 'Duas vezes',
        '3': 'De três a seis vezes',
        '4': 'De sete a menos de 12 vezes',
        '5': 'Pelo menos uma vez por mês',
        '6': 'Pelo menos uma vez por semana',
        '7': 'Quase diariamente',
    },
    'tipo_violencia': {
        '1': 'Física',
        '2': 'Sexual',
        '3': 'Psicológica',
        '4': 'Outra',
    },
    'meio_agressao': {
        '1': 'Com força corporal/espancamento (tapa, murro, beliscão, empurrão)',
        '2': 'Com arma de fogo (revólver, escopeta, pistola)',
        '3': 'Com objeto pérfuro-cortante (faca, navalha, punhal, tesoura)',
        '4': 'Com objeto contundente (pau, cassetete, barra de ferro, pedra)',
        '5': 'Com arremesso de substância/objeto quente',
        '6': 'Com lançamento de objetos',
        '7': 'Com envenenamento',
        '8': 'Por meio de palavras ofensivas, xingamentos ou palavrões',
        '9': 'Outro',
    },
    'local_ocorrencia': {
        '1': 'Residência',
        '2': 'Trabalho',
        '3': 'Escola / Faculdade ou similar',
        '4': 'Bar ou similar',
        '5': 'Via pública',
        '6': 'Outro',
    },
    'agressor': {
        '01': 'Cônjuge, companheiro(a), namorado(a)',
        '02': 'Ex-cônjuge, ex-companheiro(a), ex-namorado(a)',
        '03': 'Pai/Mãe',
        '04': 'Padrasto/Madrasta',
        '05': 'Filho(a)',
        '06': 'Irmão(ã)',
        '07': 'Outro parente',
        '08': 'Amigos(as)/colegas',
        '09': 'Patrão/chefe',
        '10': 'Outra pessoa conhecida',
    },
    'deixou_atividades': {
        '1': 'Sim',
        '2': 'Não',
    },
    'teve_lesao': {
        '1': 'Sim',
        '2': 'Não',
    },
    'buscou_saude': {
        '1': 'Sim',
        '2': 'Não',
    },
    'local_atendimento': {
        '01': 'No local da agressão',
        '02': 'Unidade básica de saúde (posto ou centro de saúde ou unidade de saúde da família)',
        '03': 'Centro de Especialidades, Policlínica pública ou PAM Posto de Assistência Médica',
        '04': 'UPA (Unidade de Pronto Atendimento)',
        '05': 'Outro tipo de Pronto Atendimento Público (24 horas)',
        '06': 'Pronto-socorro ou emergência de hospital público',
        '07': 'Hospital público/ambulatório',
        '08': 'Consultório particular ou Clínica privada',
        '09': 'Ambulatório ou consultório de empresa ou sindicato',
        '10': 'Pronto-atendimento ou emergência de hospital privado',
        '11': 'No domicílio, com médico particular',
        '12': 'No domicílio, com médico da equipe de saúde da família',
        '13': 'Outro',
    },
    'internacao_24h': {
        '1': 'Sim',
        '2': 'Não',
    },
    'teve_sequela': {
        '1': 'Sim',
        '2': 'Não',
    },
    'peso_amostral': {
        '5 dígitos e 8 casas decimais': 'Peso do morador selecionado com correção de não entrevista com calibração pela projeção de população para morador selecionado - Usado no cálculo de indicadores de morador selecionado',
    },
}


def ajuste(df):
    """Idade e peso vêm zero-preenchidos no layout posicional."""
    df["idade"] = df["idade"].str.lstrip("0").replace("", "0")
    df["peso_amostral"] = pd.to_numeric(df["peso_amostral"], errors="coerce") / 10**8
    return df


def _mulheres(df):
    return df[df["sexo"] == "Feminino"]


def preparar_conhecido(df):
    """Violência por pessoa conhecida -- o recorte doméstico/familiar."""
    r = _mulheres(df)
    r = r[r["sofreu_violencia"] == "Sim"]
    if r.empty:
        return r
    colunas = COLUNAS_COMUNS + [
        "sofreu_violencia", "frequencia_violencia", "tipo_violencia", "meio_agressao",
        "local_ocorrencia", "agressor", "deixou_atividades", "teve_lesao",
        "buscou_saude", "local_atendimento", "internacao_24h", "teve_sequela",
    ]
    r = r[colunas].copy()
    r["parceiro_intimo"] = r["agressor"].isin(AGRESSOR_PARCEIRO_INTIMO)
    return r


def preparar_desconhecido(df):
    """Violência por pessoa desconhecida -- assalto, ação policial.

    Não é violência doméstica; fica separada para não contaminar o recorte.
    """
    r = _mulheres(df)
    r = r[r["d_sofreu_violencia"] == "Sim"]
    if r.empty:
        return r
    origem = ["d_sofreu_violencia", "d_tipo_violencia", "d_meio_agressao",
              "d_local_ocorrencia", "d_agressor", "d_deixou_atividades", "d_teve_lesao",
              "d_buscou_saude", "d_local_atendimento", "d_internacao_24h", "d_teve_sequela"]
    r = r[COLUNAS_COMUNS + origem].copy()
    return r.rename(columns={c: c[2:] for c in origem})


if __name__ == "__main__":
    sys.exit(processar_pns(
        arquivo=ARQUIVO,
        posicoes=POSICOES,
        nomes=NOMES,
        dominios=DOMINIOS,
        saidas=[
            (SAIDA_CONHECIDO, preparar_conhecido),
            (SAIDA_DESCONHECIDO, preparar_desconhecido),
        ],
        pasta_bucket=PASTA_BUCKET,
        ajuste=ajuste,
    ))