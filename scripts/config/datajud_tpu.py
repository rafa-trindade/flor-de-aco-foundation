"""Assuntos da TPU (Tabela Processual Unificada do CNJ) usados no recorte.

Códigos e nomes verificados por consulta direta à API do Datajud
(api_publica_tjgo, julho/2026), com `term` em assuntos.codigo -- não
transcritos da tabela publicada. Entre parênteses, a contagem no TJGO
naquela consulta, como ordem de grandeza.

Três achados que a consulta revelou e que a tabela sozinha não mostra:

- 14226 (3 processos) e 14228 (0) são nós-pai da hierarquia, agrupadores
  que quase nunca são marcados na capa. Filtrar por eles não traz o grupo
  filho -- ficam de fora.
- 14227 e 14229 são o MESMO assunto com grafias diferentes na tabela
  oficial ("Medida Protetiva  de Urgência", com espaço duplo, vs. grafia
  normal). Os dois precisam entrar, senão perdem-se os 25 do 14229.
- assuntos é ARRAY: um processo carrega vários códigos ao mesmo tempo.
  Filtrar por 12091 traz também os rotulados "Crime Tentado" e "Homicídio
  Qualificado" que tenham 12091 no array -- ou seja, a tentativa de
  feminicídio entra, que é o que se quer.
"""

# Núcleo do projeto. Assunto específico, sem ambiguidade.
FEMINICIDIO = {
    12091: "Feminicídio",  # (2.362)
}

# Violência de gênero tipificada. Cada código nomeia uma conduta
# específica contra a mulher -- não são transversais.
VIOLENCIA_TIPIFICADA = {
    14943: "Lesão Cometida em Razão da Condição de Mulher",  # (10.000+)
    14942: "Violência Psicológica contra a Mulher",
    14944: "Análogo à Violência Psicológica contra a Mulher",
    14684: "Perseguição",  # (6.066)
}

# Medida protetiva da Lei Maria da Penha. O dado de prevenção: existe
# antes do desfecho fatal, e o descumprimento é sinal de escalada.
MEDIDA_PROTETIVA = {
    14227: "Crime de Descumprimento de Medida Protetiva  de Urgência",  # (10.000+)
    14229: "Descumprimento de Medida Protetiva de Urgência",  # (25) -- mesma coisa, outra grafia
}

# Assuntos TRANSVERSAIS: marcados junto com o crime específico (ameaça,
# dano, furto, crimes de trânsito...) para sinalizar contexto doméstico.
# Sozinhos, puxam todo processo criminal com mulher envolvida -- 10.000+
# no TJGO cada, milhões no país.
#
# Não entram no recorte por si só. Viram flag no process quando aparecem
# junto de um assunto do recorte, preservando o contexto sem inflar a base.
# A TPU repete o mesmo assunto com grafias variantes, e mapear só uma
# perde casos: um processo marcado apenas com 10948 saía sem a flag de
# contexto doméstico. Os pares foram descobertos consultando os assuntos
# que acompanham o recorte na base, não a tabela publicada.
CONTEXTO_DOMESTICO = {
    10949: "Violência Doméstica Contra a Mulher",  # (10.000+)
    10948: "Violência Doméstica Contra a Mulher",  # mesma coisa, outro código
    12194: "Contra a Mulher",  # (10.000+)
    12196: "Contra a mulher",  # idem, com minúscula na tabela oficial
    5560: "Decorrente de Violência Doméstica",
}

# Contra-recorte: a vítima explicitamente NÃO é mulher. Excluir.
NAO_MULHER = {
    12195: "Contra pessoas não identificadas como mulher",  # (1.156)
}

# Nós-pai da hierarquia TPU. Documentados para que ninguém os inclua
# achando que capturam o grupo -- não capturam.
AGRUPADORES_INUTEIS = {
    14226: "Crimes Previstos na Lei Maria da Penha",  # (3)
    14228: "Previstos na Lei Maria da Penha",  # (0)
}

# Qualificadores que aparecem junto, úteis como marcador de gravidade
# mas inúteis como recorte (não são específicos de violência de gênero).
QUALIFICADORES = {
    5555: "Crime Tentado",
}

# Assuntos que só existem quando a morte ocorreu -- não há como ocultar
# cadáver de quem sobreviveu. São o único indício POSITIVO de consumação
# disponível na capa do processo: o Datajud não traz campo de desfecho, e
# a ausência de "Crime Tentado" não prova consumação (o tribunal pode
# simplesmente não ter marcado).
#
# Códigos verificados na API, aparecendo junto de 12091.
INDICIO_CONSUMACAO = {
    3458: "Destruição / Subração / Ocultação de Cadáver",
}


# CLASSES processuais, não assuntos. A distinção importa:
#
# - classe 1268: o processo É um pedido de medida protetiva
# - assunto 14227/14229: houve DESCUMPRIMENTO de uma protetiva
#
# São coisas diferentes e não coincidem. Há processos de classe 1268 cujo
# único assunto é 10949 (violência doméstica), sem marcador de
# descumprimento -- filtrar protetiva só por assunto os perderia.
#
# Só as classes da Lei Maria da Penha entram: a mesma consulta revelou
# protetivas do Estatuto do Idoso (10967, 12424) e da Lei 13.431, de
# criança e adolescente (14734), que aparecem no recorte por coocorrerem
# com assunto de violência doméstica mas protegem outra pessoa.
CLASSES_MEDIDA_PROTETIVA = {
    1268: "Medidas Protetivas de urgência (Lei Maria da Penha) Criminal",
    # Mesmo instituto, rito infracional -- agressor adolescente.
    12423: "Medidas Protetivas de Urgência (Lei Maria da Penha) Infracional",
}

# Protetivas de outros estatutos. Documentadas para que ninguém as
# inclua achando que são da Lei Maria da Penha.
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


# Todos os assuntos com nome conhecido, para rotular a saída.
NOMES = _nomes(
    FEMINICIDIO, VIOLENCIA_TIPIFICADA, MEDIDA_PROTETIVA,
    CONTEXTO_DOMESTICO, NAO_MULHER, AGRUPADORES_INUTEIS, QUALIFICADORES,
    INDICIO_CONSUMACAO,
)

# Ordem de leitura dos assuntos na coluna ASSUNTOS. Alfabética esconde a
# informação que importa: "Crime Tentado, Feminicídio, Homicídio
# Qualificado" diz de imediato que é tentativa, enquanto a ordem
# alfabética espalha forma, tipo e qualificadora ao acaso.
#
# Menor valor sai primeiro; assunto fora desta lista vai para o fim, em
# ordem alfabética.
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

# Recortes nomeados. O extract recebe um deles; começar pelo menor valida
# o pipeline inteiro (checkpoint, retry, merge) em minutos em vez de dias.
RECORTES = {
    # ~45k movimentações no país. Valida o pipeline com volume de uma
    # sessão de extração.
    "feminicidio": list(FEMINICIDIO),
    # Violência de gênero com tipificação própria: o desfecho
    # (feminicídio), a escalada (protetiva descumprida) e as condutas
    # tipificadas contra a mulher. Cada código nomeia algo específico --
    # é o que separa este recorte do `amplo`, cujos transversais só
    # marcam contexto. Centenas de milhares de movimentações.
    "violencia_genero": (list(FEMINICIDIO) + list(VIOLENCIA_TIPIFICADA)
                         + list(MEDIDA_PROTETIVA)),
    # Acrescenta os marcadores transversais de contexto: todo processo
    # criminal em que a vítima é mulher em contexto doméstico, inclusive
    # ameaça, dano, furto e crimes de trânsito. Milhões de registros --
    # o assunto 10949 sozinho tinha 154 mil no TJGO, contra 2.359 do
    # feminicídio.
    "contexto_domestico": (list(FEMINICIDIO) + list(VIOLENCIA_TIPIFICADA)
                           + list(MEDIDA_PROTETIVA)
                           + list(CONTEXTO_DOMESTICO)),
}