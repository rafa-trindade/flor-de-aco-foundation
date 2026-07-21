"""Mapeamento CID-10: Capítulo XX, grupo X85-Y09 (Agressões).

Regras de negócio:
- Caracteres 1-3: Método da agressão.
- Caractere 4: Local da ocorrência (exceção: Y06/Y07 subdividem por agressor).
- Exceção médica: Y35 (intervenção legal) é formalmente excluído deste grupo pela CID-10.
"""

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

CID_AGRESSOR = {
    "0": "Esposo ou companheiro",
    "1": "Pais",
    "2": "Conhecido ou amigo",
    "3": "Autoridades oficiais",
    "8": "Outra pessoa especificada",
    "9": "Pessoa não especificada",
}

CATEGORIAS_SUBDIVIDIDAS_POR_AGRESSOR = {"Y06", "Y07"}

_SUFIXOS_LOCAL = list(CID_LOCAL.keys())
_SUFIXOS_AGRESSOR_Y06 = ["0", "1", "2", "8", "9"]
_SUFIXOS_AGRESSOR_Y07 = ["0", "1", "2", "3", "8", "9"]


def _sufixos_validos(categoria: str) -> list[str]:
    if categoria == "Y06":
        return _SUFIXOS_AGRESSOR_Y06
    if categoria == "Y07":
        return _SUFIXOS_AGRESSOR_Y07
    return _SUFIXOS_LOCAL


# Inclui intencionalmente os códigos de 3 caracteres: 
# o banco de dados do SIM frequentemente omite a subdivisão.
CODIGOS_AGRESSAO: set[str] = set(CID_METODO.keys())
for _cat in CID_METODO:
    for _suf in _sufixos_validos(_cat):
        CODIGOS_AGRESSAO.add(f"{_cat}{_suf}")


def decompor(codigo: str) -> tuple[str | None, str | None, str | None]:
    """Retorna tupla (metodo, local, agressor).

    Nota: `local` e `agressor` são mutuamente exclusivos com base na categoria.
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