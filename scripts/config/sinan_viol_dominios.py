"""Domínios dos campos categóricos da ficha VIOL (SINAN NET 5.0/Patch 5.1).

Transcritos do "Dicionário de Dados -- SINAN NET -- Versão 5.0/Patch 5.1",
Violência Interpessoal/Autoprovocada, revisado junho/2015.

Duas divergências entre o PDF e o DBF, tratadas aqui:

- ESCOLARIDADE: o PDF imprime "43 Analfabeto" seguido de "1. 1ª a 4ª série
  incompleta...", deslocando toda a numeração visual. O código gravado no
  DBF é 0 para Analfabeto e a sequência segue 1..10.
- VIOLENCIA_MOTIVADA e LOCAL_OCORRENCIA: declarados varchar2(1) no PDF mas
  com categorias de dois dígitos (88, 99). A largura efetiva varia entre
  competências, daí as chaves com e sem zero à esquerda.

O layout anterior a 2015 não tem IDENT_GEN, VIOL_MOTIV nem os DEF_*; nesses
anos as colunas chegam ausentes e viram NULL no union_by_name.
"""

# Domínio Sim/Não/Ignorado, repetido em dezenas de campos da ficha.
SIM_NAO = {"1": "SIM", "2": "NAO", "9": "IGNORADO"}

# Variante com "não se aplica", usada nos campos condicionais (violência
# sexual, deficiências, procedimentos).
SIM_NAO_NA = {"1": "SIM", "2": "NAO", "8": "NAO SE APLICA", "9": "IGNORADO"}

SEXO = {"M": "MASCULINO", "F": "FEMININO", "I": "IGNORADO"}

RACA_COR = {
    "1": "BRANCA",
    "2": "PRETA",
    "3": "AMARELA",
    "4": "PARDA",
    "5": "INDIGENA",
    "9": "IGNORADO",
}

GESTANTE = {
    "1": "1o TRIMESTRE",
    "2": "2o TRIMESTRE",
    "3": "3o TRIMESTRE",
    "4": "IDADE GESTACIONAL IGNORADA",
    "5": "NAO",
    "6": "NAO SE APLICA",
    "9": "IGNORADO",
}

ESCOLARIDADE = {
    "0": "ANALFABETO",
    "1": "1a A 4a SERIE INCOMPLETA DO EF",
    "2": "4a SERIE COMPLETA DO EF",
    "3": "5a A 8a SERIE INCOMPLETA DO EF",
    "4": "ENSINO FUNDAMENTAL COMPLETO",
    "5": "ENSINO MEDIO INCOMPLETO",
    "6": "ENSINO MEDIO COMPLETO",
    "7": "EDUCACAO SUPERIOR INCOMPLETA",
    "8": "EDUCACAO SUPERIOR COMPLETA",
    "9": "IGNORADO",
    "10": "NAO SE APLICA",
}

SITUACAO_CONJUGAL = {
    "1": "SOLTEIRA",
    "2": "CASADA / UNIAO CONSENSUAL",
    "3": "VIUVA",
    "4": "SEPARADA",
    "8": "NAO SE APLICA",
    "9": "IGNORADO",
}

ORIENTACAO_SEXUAL = {
    "1": "HETEROSSEXUAL",
    "2": "HOMOSSEXUAL (GAY/LESBICA)",
    "3": "BISSEXUAL",
    "8": "NAO SE APLICA",
    "9": "IGNORADO",
}

IDENTIDADE_GENERO = {
    "1": "TRAVESTI",
    "2": "TRANSEXUAL MULHER",
    "3": "TRANSEXUAL HOMEM",
    "8": "NAO SE APLICA",
    "9": "IGNORADO",
}

ZONA = {"1": "URBANA", "2": "RURAL", "3": "PERIURBANA", "9": "IGNORADO"}

LOCAL_OCORRENCIA = {
    "1": "RESIDENCIA", "01": "RESIDENCIA",
    "2": "HABITACAO COLETIVA", "02": "HABITACAO COLETIVA",
    "3": "ESCOLA", "03": "ESCOLA",
    "4": "LOCAL DE PRATICA ESPORTIVA", "04": "LOCAL DE PRATICA ESPORTIVA",
    "5": "BAR OU SIMILAR", "05": "BAR OU SIMILAR",
    "6": "VIA PUBLICA", "06": "VIA PUBLICA",
    "7": "COMERCIO/SERVICOS", "07": "COMERCIO/SERVICOS",
    "8": "INDUSTRIAS/CONSTRUCAO", "08": "INDUSTRIAS/CONSTRUCAO",
    "9": "OUTRO", "09": "OUTRO",
    "99": "IGNORADO",
}

VIOLENCIA_MOTIVADA = {
    "1": "SEXISMO", "01": "SEXISMO",
    "2": "HOMOFOBIA/LESBOFOBIA/BIFOBIA/TRANSFOBIA",
    "02": "HOMOFOBIA/LESBOFOBIA/BIFOBIA/TRANSFOBIA",
    "3": "RACISMO", "03": "RACISMO",
    "4": "INTOLERANCIA RELIGIOSA", "04": "INTOLERANCIA RELIGIOSA",
    "5": "XENOFOBIA", "05": "XENOFOBIA",
    "6": "CONFLITO GERACIONAL", "06": "CONFLITO GERACIONAL",
    "7": "SITUACAO DE RUA", "07": "SITUACAO DE RUA",
    "8": "DEFICIENCIA", "08": "DEFICIENCIA",
    "9": "OUTROS", "09": "OUTROS",
    "88": "NAO SE APLICA",
    "99": "IGNORADO",
}

NUMERO_ENVOLVIDOS = {"1": "UM", "2": "DOIS OU MAIS", "9": "IGNORADO"}

SEXO_AGRESSOR = {
    "1": "MASCULINO",
    "2": "FEMININO",
    "3": "AMBOS OS SEXOS",
    "9": "IGNORADO",
}

# Campo 64. O DBF grava em CICL_VID; CICL_VID_AUTOR (nome do PDF) existe
# no schema mas chega sempre nulo. Ler só o do PDF deixaria a coluna vazia
# em silêncio -- o process usa COALESCE(CICL_VID, CICL_VID_AUTOR).
CICLO_VIDA_AGRESSOR = {
    "1": "CRIANCA",
    "2": "ADOLESCENTE",
    "3": "JOVEM",
    "4": "PESSOA ADULTA",
    "5": "PESSOA IDOSA",
    "9": "IGNORADO",
}

UNIDADE_NOTIFICADORA = {
    "1": "UNIDADE DE SAUDE",
    "2": "UNIDADE DE ASSISTENCIA SOCIAL",
    "3": "ESTABELECIMENTO DE ENSINO",
    "4": "CONSELHO TUTELAR",
    "5": "UNIDADE DE SAUDE INDIGENA",
    "6": "CENTRO ESPECIALIZADO DE ATENDIMENTO A MULHER",
    "7": "OUTROS",
}

# Campo 61 -- relação com o provável autor. Multimarcação: a ficha permite
# vários "Sim" na mesma notificação (campo 60 NUM_ENVOLV registra "dois ou
# mais"). Vira LIST no Parquet, não coluna única -- não há vínculo
# "principal" na ficha, e eleger um seria inventar hierarquia.
VINCULO_AGRESSOR = {
    "REL_PAI": "PAI",
    "REL_MAE": "MAE",
    "REL_PAD": "PADRASTO",
    "REL_MAD": "MADRASTA",
    "REL_CONJ": "CONJUGE",
    "REL_EXCON": "EX-CONJUGE",
    "REL_NAMO": "NAMORADO(A)",
    "REL_EXNAM": "EX-NAMORADO(A)",
    "REL_FILHO": "FILHO(A)",
    "REL_IRMAO": "IRMAO(A)",
    "REL_CONHEC": "AMIGOS/CONHECIDOS",
    "REL_DESCO": "DESCONHECIDO",
    "REL_CUIDA": "CUIDADOR",
    "REL_PATRAO": "PATRAO/CHEFE",
    "REL_INST": "RELACAO INSTITUCIONAL",
    "REL_POL": "POLICIAL/AGENTE DA LEI",
    "REL_PROPRI": "PROPRIA PESSOA",
    "REL_OUTROS": "OUTROS",
}

# Subconjunto de VINCULO_AGRESSOR que caracteriza parceiro íntimo, atual ou
# anterior. Base do recorte de violência por parceiro íntimo -- o critério
# que o SIM não permite, por não haver relação vítima-agressor na DO.
VINCULOS_PARCEIRO_INTIMO = [
    "REL_CONJ", "REL_EXCON", "REL_NAMO", "REL_EXNAM",
]

# Vínculo familiar não-parceiro. Separado do íntimo porque o perfil de
# violência intrafamiliar contra meninas é distinto do de parceiro.
VINCULOS_FAMILIARES = [
    "REL_PAI", "REL_MAE", "REL_PAD", "REL_MAD", "REL_FILHO", "REL_IRMAO",
]

# Campo 56 -- tipo de violência. Multimarcação, mesma lógica do campo 61.
TIPO_VIOLENCIA = {
    "VIOL_FISIC": "FISICA",
    "VIOL_PSICO": "PSICOLOGICA/MORAL",
    "VIOL_TORT": "TORTURA",
    "VIOL_SEXU": "SEXUAL",
    "VIOL_TRAF": "TRAFICO DE SERES HUMANOS",
    "VIOL_FINAN": "FINANCEIRA/ECONOMICA",
    "VIOL_NEGLI": "NEGLIGENCIA/ABANDONO",
    "VIOL_INFAN": "TRABALHO INFANTIL",
    "VIOL_LEGAL": "INTERVENCAO LEGAL",
    "VIOL_OUTR": "OUTROS",
}

# Campo 57 -- meio de agressão. Multimarcação.
MEIO_AGRESSAO = {
    "AG_FORCA": "FORCA CORPORAL/ESPANCAMENTO",
    "AG_ENFOR": "ENFORCAMENTO",
    "AG_OBJETO": "OBJETO CONTUNDENTE",
    "AG_CORTE": "OBJETO PERFURO-CORTANTE",
    "AG_QUENTE": "SUBSTANCIA/OBJETO QUENTE",
    "AG_ENVEN": "ENVENENAMENTO/INTOXICACAO",
    "AG_FOGO": "ARMA DE FOGO",
    "AG_AMEACA": "AMEACA",
    "AG_OUTROS": "OUTRO",
}

# Campo 58 -- natureza da violência sexual. Só preenchido quando
# VIOL_SEXU=1; nos demais casos o sistema grava 8 (não se aplica).
TIPO_VIOLENCIA_SEXUAL = {
    "SEX_ASSEDI": "ASSEDIO SEXUAL",
    "SEX_ESTUPR": "ESTUPRO",
    "SEX_PORNO": "PORNOGRAFIA INFANTIL",
    "SEX_EXPLO": "EXPLORACAO SEXUAL",
    "SEX_OUTRO": "OUTRO",
}

# Campo 65 -- encaminhamentos da rede. Multimarcação.
#
# Os nomes efetivos no DBF divergem do PDF em três pontos, verificados no
# schema dos arquivos: REDE_SAU (o PDF diz ENC_SAUDE) e DELEG_IDOS (o PDF
# diz DELEG_IDOSO). As duas grafias entram no mapa porque o layout varia
# entre competências e a ausente vira NULL, sem efeito no list_filter.
#
# Não confundir com o bloco ENC_* legado (ENC_TUTELA, ENC_DEAM, ENC_IML
# etc.), presente até ~2017 e substituído por estes campos.
ENCAMINHAMENTO = {
    "REDE_SAU": "REDE DA SAUDE",
    "ENC_SAUDE": "REDE DA SAUDE",
    "ASSIST_SOC": "REDE DA ASSISTENCIA SOCIAL",
    "REDE_EDUCA": "REDE DE EDUCACAO",
    "ATEND_MULH": "REDE DE ATENDIMENTO A MULHER",
    "CONS_TUTEL": "CONSELHO TUTELAR",
    "CONS_IDO": "CONSELHO DO IDOSO",
    "DELEG_IDOS": "DELEGACIA DE ATENDIMENTO AO IDOSO",
    "DELEG_IDOSO": "DELEGACIA DE ATENDIMENTO AO IDOSO",
    "DIR_HUMAN": "CENTRO DE REFERENCIA DOS DIREITOS HUMANOS",
    "MPU": "MINISTERIO PUBLICO",
    "DELEG_CRIA": "DELEGACIA DE PROTECAO A CRIANCA E ADOLESCENTE",
    "DELEG_MULH": "DELEGACIA DE ATENDIMENTO A MULHER",
    "DELEG": "OUTRAS DELEGACIAS",
    "INFAN_JUV": "JUSTICA DA INFANCIA E DA JUVENTUDE",
    "DEFEN_PUBL": "DEFENSORIA PUBLICA",
}

# Campo 39 -- deficiências e transtornos. Multimarcação, condicionada a
# DEF_TRANS=1.
DEFICIENCIA = {
    "DEF_FISICA": "DEFICIENCIA FISICA",
    "DEF_MENTAL": "DEFICIENCIA INTELECTUAL",
    "DEF_VISUAL": "DEFICIENCIA VISUAL",
    "DEF_AUDITI": "DEFICIENCIA AUDITIVA",
    "TRAN_MENT": "TRANSTORNO MENTAL",
    "TRAN_COMP": "TRANSTORNO DE COMPORTAMENTO",
    "DEF_OUT": "OUTRAS DEFICIENCIAS/SINDROMES",
}