"""Domínios dos campos categóricos do SIM/DATASUS.

Valores conforme a documentação da Declaração de Óbito. O código 9
(Ignorado) existe na maioria dos campos e é mapeado explicitamente em vez
de virar NULL -- "ignorado" é informação diferente de "ausente".
"""

SEXO = {"1": "MASCULINO", "2": "FEMININO", "0": "IGNORADO", "9": "IGNORADO"}

RACA_COR = {
    "1": "BRANCA",
    "2": "PRETA",
    "3": "AMARELA",
    "4": "PARDA",
    "5": "INDIGENA",
    "9": "IGNORADO",
}

ESTADO_CIVIL = {
    "1": "SOLTEIRA",
    "2": "CASADA",
    "3": "VIUVA",
    "4": "SEPARADA JUDICIALMENTE / DIVORCIADA",
    "5": "UNIAO ESTAVEL",
    "9": "IGNORADO",
}

LOCAL_OCORRENCIA = {
    "1": "HOSPITAL",
    "2": "OUTROS ESTABELECIMENTOS DE SAUDE",
    "3": "DOMICILIO",
    "4": "VIA PUBLICA",
    "5": "OUTROS",
    "6": "ALDEIA INDIGENA",
    "9": "IGNORADO",
}

CIRCUNSTANCIA_OBITO = {
    "1": "ACIDENTE",
    "2": "SUICIDIO",
    "3": "HOMICIDIO",
    "4": "OUTROS",
    "9": "IGNORADO",
}

OBITO_GRAVIDEZ = {"1": "SIM", "2": "NAO", "9": "IGNORADO"}

OBITO_PUERPERIO = {
    "1": "SIM, ATE 42 DIAS APOS O PARTO",
    "2": "SIM, DE 43 DIAS A 1 ANO APOS O PARTO",
    "3": "NAO",
    "9": "IGNORADO",
}