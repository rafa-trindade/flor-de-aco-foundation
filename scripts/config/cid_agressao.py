"""CID-10, grupo X85-Y09 (Agressões), Capítulo XX.

Estrutura real da classificação, que o dicionário anterior do projeto não
seguia: os 3 primeiros caracteres definem o MÉTODO da agressão, e o 4º
caractere subdivide.

O 4º caractere tem dois significados diferentes:
  - X85-Y05, Y08, Y09 -> LOCAL de ocorrência (.0 residência ... .9 n/e)
  - Y06, Y07          -> AGRESSOR (.0 esposo/companheiro, .1 pais ...)

Y06/Y07 são especialmente relevantes aqui: Y060 e Y070 identificam
explicitamente violência por parceiro íntimo.

Y35 (intervenção legal) NÃO faz parte deste grupo -- a própria CID-10 o
lista como exclusão de X85-Y09. São mortes por ação do Estado, categoria
conceitualmente distinta de agressão interpessoal.

Fonte: CID-10 Cap. XX, grupo X85-Y09 (OMS / DATASUS).
"""

# 3 primeiros caracteres -> método da agressão
CID_METODO = {
    "X85": "Agressão por meio de drogas, medicamentos e substâncias biológicas",
    "X86": "Agressão por meio de substâncias corrosivas",
    "X87": "Agressão por pesticidas",
    "X88": "Agressão por meio de gases e vapores",
    "X89": "Agressão por meio de outros produtos químicos e substâncias nocivas especificados",
    "X90": "Agressão por meio de produtos químicos e substâncias nocivas não especificados",
    "X91": "Agressão por meio de enforcamento, estrangulamento e sufocação",
    "X92": "Agressão por meio de afogamento e submersão",
    "X93": "Agressão por meio de disparo de arma de fogo de mão",
    "X94": "Agressão por meio de disparo de espingarda, carabina ou arma de fogo de maior calibre",
    "X95": "Agressão por meio de disparo de outra arma de fogo ou de arma não especificada",
    "X96": "Agressão por meio de material explosivo",
    "X97": "Agressão por meio de fumaça, fogo e chamas",
    "X98": "Agressão por meio de vapor de água, gases ou objetos quentes",
    "X99": "Agressão por meio de objeto cortante ou penetrante",
    "Y00": "Agressão por meio de um objeto contundente",
    "Y01": "Agressão por meio de projeção de um lugar elevado",
    "Y02": "Agressão por meio de projeção ou colocação da vítima diante de um objeto em movimento",
    "Y03": "Agressão por meio de impacto de um veículo a motor",
    "Y04": "Agressão por meio de força corporal",
    "Y05": "Agressão sexual por meio de força física",
    "Y06": "Negligência e abandono",
    "Y07": "Outras síndromes de maus tratos",
    "Y08": "Agressão por outros meios especificados",
    "Y09": "Agressão por meios não especificados",
}

# 4º caractere na maioria das categorias
CID_LOCAL = {
    "0": "Residência",
    "1": "Habitação coletiva",
    "2": "Escolas, outras instituições e áreas de administração pública",
    "3": "Área para a prática de esportes e atletismo",
    "4": "Rua e estrada",
    "5": "Áreas de comércio e de serviços",
    "6": "Áreas industriais e em construção",
    "7": "Fazenda",
    "8": "Outros locais especificados",
    "9": "Local não especificado",
}

# 4º caractere em Y06 e Y07
CID_AGRESSOR = {
    "0": "Esposo ou companheiro",
    "1": "Pais",
    "2": "Conhecido ou amigo",
    "3": "Autoridades oficiais",
    "8": "Outra pessoa especificada",
    "9": "Pessoa não especificada",
}

CATEGORIAS_SUBDIVIDIDAS_POR_AGRESSOR = {"Y06", "Y07"}

# Subcategorias que existem de fato em cada categoria
_SUFIXOS_LOCAL = list(CID_LOCAL.keys())
_SUFIXOS_AGRESSOR_Y06 = ["0", "1", "2", "8", "9"]
_SUFIXOS_AGRESSOR_Y07 = ["0", "1", "2", "3", "8", "9"]


def _sufixos_validos(categoria: str) -> list[str]:
    if categoria == "Y06":
        return _SUFIXOS_AGRESSOR_Y06
    if categoria == "Y07":
        return _SUFIXOS_AGRESSOR_Y07
    return _SUFIXOS_LOCAL


# Todos os códigos de 4 caracteres válidos do grupo -- usado no filtro.
# Inclui também os de 3 caracteres: o SIM às vezes registra a categoria
# sem a subdivisão.
CODIGOS_AGRESSAO: set[str] = set(CID_METODO.keys())
for _cat in CID_METODO:
    for _suf in _sufixos_validos(_cat):
        CODIGOS_AGRESSAO.add(f"{_cat}{_suf}")


def decompor(codigo: str) -> tuple[str | None, str | None, str | None]:
    """(metodo, local, agressor) a partir do CAUSABAS.

    Devolve (None, None, None) se o código não for do grupo de agressões.
    local e agressor são mutuamente exclusivos -- depende da categoria.
    """
    if not codigo:
        return None, None, None

    codigo = codigo.strip().upper()
    categoria = codigo[:3]
    metodo = CID_METODO.get(categoria)
    if metodo is None:
        return None, None, None

    if len(codigo) < 4:
        return metodo, None, None

    sufixo = codigo[3]
    if categoria in CATEGORIAS_SUBDIVIDIDAS_POR_AGRESSOR:
        return metodo, None, CID_AGRESSOR.get(sufixo)
    return metodo, CID_LOCAL.get(sufixo), None