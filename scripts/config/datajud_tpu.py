"""Mapeamento de assuntos da TPU (CNJ) verificados via API do Datajud (jul/2026).

Notas técnicas críticas da API (comportamentos não documentados na tabela oficial):
- Hierarquia não propaga: Nós-pai (14226, 14228) não trazem os filhos na busca.
- Duplicidade oficial: 14227 e 14229 são o mesmo assunto com espaçamento diferente. Ambos são obrigatórios.
- Busca em Array: Filtrar por um código (ex: 12091) captura todos os assuntos do processo, mantendo qualificadoras úteis no retorno (ex: Crime Tentado).
"""

FEMINICIDIO = {
    12091: "Feminicídio",  # (2.362)
}

# Condutas específicas contra a mulher (não transversais).
VIOLENCIA_TIPIFICADA = {
    14943: "Lesão Cometida em Razão da Condição de Mulher",  # (10.000+)
    14942: "Violência Psicológica contra a Mulher",
    14944: "Análogo à Violência Psicológica contra a Mulher",
    14684: "Perseguição",  # (6.066)
}

MEDIDA_PROTETIVA = {
    14227: "Crime de Descumprimento de Medida Protetiva  de Urgência",  # (10.000+)
    14229: "Descumprimento de Medida Protetiva de Urgência",  # (25) -- mesma coisa, outra grafia
}

# Assuntos TRANSVERSAIS.
# Uso técnico: Devem virar flags de contexto durante o processamento. 
# NÃO usar como filtro isolado de extração para não inflar a base (milhões de registros).
# Contém pares com grafias variantes descobertos via API (ex: 10949/10948).
CONTEXTO_DOMESTICO = {
    10949: "Violência Doméstica Contra a Mulher",  # (10.000+)
    10948: "Violência Doméstica Contra a Mulher",  # mesma coisa, outro código
    12194: "Contra a Mulher",  # (10.000+)
    12196: "Contra a mulher",  # idem, com minúscula na tabela oficial
    5560: "Decorrente de Violência Doméstica",
}

NAO_MULHER = {
    12195: "Contra pessoas não identificadas como mulher",  # (1.156)
}

# Nós-pai da TPU. Não incluir nas buscas (não propagam para os filhos na API).
AGRUPADORES_INUTEIS = {
    14226: "Crimes Previstos na Lei Maria da Penha",  # (3)
    14228: "Previstos na Lei Maria da Penha",  # (0)
}

QUALIFICADORES = {
    5555: "Crime Tentado",
}

# Único indício positivo de consumação na capa do processo (Datajud não possui campo de desfecho).
# A ausência de "Crime Tentado" não garante consumação devido a subnotificações dos tribunais.
INDICIO_CONSUMACAO = {
    3458: "Destruição / Subração / Ocultação de Cadáver",
}


# CLASSES processuais (distintas de assuntos).
# Classe 1268 = Pedido de medida. Assunto 14227 = Descumprimento de medida.
# Atenção: Filtrar protetiva apenas por assunto perde processos onde só a classe foi preenchida.
# Limitado estritamente à Lei Maria da Penha.
CLASSES_MEDIDA_PROTETIVA = {
    1268: "Medidas Protetivas de urgência (Lei Maria da Penha) Criminal",
    # Mesmo instituto, rito infracional -- agressor adolescente.
    12423: "Medidas Protetivas de Urgência (Lei Maria da Penha) Infracional",
}

CLASSES_PROTETIVA_OUTROS = {
    10967: "Medidas Protetivas - Estatuto do Idoso Criminal",
    12424: "Medidas Protetivas - Estatuto do Idoso Infracional",
    14734: "Medidas Protetivas - Criança e Adolescente (Lei 13.431)",
}


def _nomes(*grupos: dict) -> dict:
    reunido = {}
    for g in grupos:
        reunido.update(g)
    return reunido


NOMES = _nomes(
    FEMINICIDIO, VIOLENCIA_TIPIFICADA, MEDIDA_PROTETIVA,
    CONTEXTO_DOMESTICO, NAO_MULHER, AGRUPADORES_INUTEIS, QUALIFICADORES,
    INDICIO_CONSUMACAO,
)

# Ordenação de leitura (menor valor priorizado).
# Evita a ordenação alfabética padrão que dispersa o contexto crítico do crime.
# Assuntos omitidos vão para o fim em ordem alfabética.
PRIORIDADE_LEITURA = {
    # forma do crime
    5555: 10,
    # tipo penal
    3372: 20, 3370: 21, 3371: 22, 3458: 23,
    # qualificadora de gênero -- o núcleo do recorte
    12091: 30,
    14943: 31,
    14942: 32, 14944: 32,
    14684: 33,
    14227: 34, 14229: 34,
    # contexto
    10949: 40, 10948: 40,
    12194: 41, 12196: 41,
    5560: 42,
}

# Recortes de extração. O uso do recorte 'feminicidio' (menor volume) 
# permite validar o pipeline ponta a ponta rapidamente.
RECORTES = {

    "feminicidio": list(FEMINICIDIO),

    "violencia_genero": (list(FEMINICIDIO) + list(VIOLENCIA_TIPIFICADA)
                         + list(MEDIDA_PROTETIVA)),

    "contexto_domestico": (list(FEMINICIDIO) + list(VIOLENCIA_TIPIFICADA)
                           + list(MEDIDA_PROTETIVA)
                           + list(CONTEXTO_DOMESTICO)),
}