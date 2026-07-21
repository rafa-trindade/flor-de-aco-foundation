"""CNJ/Datajud -- processos judiciais de violência contra a mulher.

Metadados processuais (capa e movimentos), não dados da vítima: a API não
expõe partes. Mede judicialização e tramitação -- quantos processos, onde,
em que fase --, complementando o SIM (óbito) e o SINAN (notificação).

A API é lenta e limitada: ~10-30s por resposta, 429 em requisição
sequencial, 504 em consulta cara, teto de 10.000 por página. Daí o
checkpoint: a extração é retomável, e uma rodada interrompida continua de
onde parou em vez de recomeçar.

A consulta é fatiada por ano de ajuizamento: paginar milhares de
registros numa sequência só faz o cluster percorrer cada vez mais do
índice, e a rejeição cresce a cada página.

Uso:
    python -m scripts.extract.datajud.fetch_datajud_violencia [recorte] [tribunais] [flags]

    recorte:        feminicidio (padrão) | gravidade | amplo
    tribunais:      lista separada por vírgula (padrão: todos os TJs)
    --reset:        limpa checkpoint e NDJSON antes, forçando reextração
    --incremental:  reconsulta só o ano corrente e o anterior, trazendo
                    o que entrou desde a última rodada
    --paralelismo=N tribunais simultâneos (padrão 4; use 1 para serial)

    # carga inicial de um tribunal
    python -m scripts.extract.datajud.fetch_datajud_violencia feminicidio tjgo

    # atualização periódica
    python -m scripts.extract.datajud.fetch_datajud_violencia feminicidio tjgo --incremental
"""
import json
import logging
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import requests

from scripts.common.paths import MANUAL_DIR
from scripts.common import exit_codes
from scripts.common.bucket_sync import get_s3_client
from scripts.common import env as env_comum
from scripts.config.datajud_tpu import RECORTES, NAO_MULHER

logger = logging.getLogger(__name__)

URL_BASE = "https://api-publica.datajud.cnj.jus.br"

# Chave pública, publicada aberta na wiki do CNJ. Pode ser trocada pelo
# CNJ a qualquer momento -- em 401, buscar a vigente em
# https://datajud-wiki.cnj.jus.br/api-publica/acesso
API_KEY = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="

# MANUAL_DIR, não LANDING_DIR: landing é scratch e sofre limpeza, e
# reextrair custa horas contra uma API instável -- o NDJSON bruto é o
# backup barato dessa coleta.
OUTPUT_DIR = MANUAL_DIR / "datajud"
PASTA_BUCKET = "datajud"

# Registros por resposta. O teto da API é 10.000.
#
# 2.000 é meio-termo: o custo dominante da extração é o NÚMERO de
# requisições (10-30s de resposta cada, mais pausa), não o tamanho delas
# -- com 500, um tribunal de 90 mil precisava de 180 idas à API; com
# 2.000 são 45. Páginas maiores podem sofrer mais rejeição de shard, e o
# checkpoint salva por página, então uma falha custa mais trabalho
# perdido: se o log mostrar muito descarte, baixar de novo.
TAMANHO_PAGINA = 2_000

# Pausa entre páginas no caso normal. O backoff cobre a rejeição quando
# ela vem; pausar muito por precaução só alonga a extração -- o TJAC
# rodou 11 fatias seguidas sem um único warning.
PAUSA_ENTRE_PAGINAS = 2

# Retry. A rejeição é por fila cheia no cluster, não throttling por
# cliente: é aleatória, e esperar mais não aumenta a chance de passar.
# Backoff longo só desperdiça tempo -- no TJGO, 85% do relógio foi espera
# entre tentativas, não download. Espera curta com jitter (para não
# sincronizar as retentativas) e mais tentativas rende muito mais.
MAX_TENTATIVAS = 15
ESPERA_RETRY = 4
ESPERA_MAXIMA = 20

# Tribunais extraídos ao mesmo tempo. Cada um é um índice distinto no
# cluster, então não competem pelo mesmo shard. Subir demais aumenta a
# fila do Elasticsearch (que é compartilhada) e o retorno cai; 4 é um
# meio-termo conservador. Ajustável por --paralelismo N.
PARALELISMO = 4

# Contagem exata do Elasticsearch para em 10.000: acima disso
# hits.total.relation vira "gte" e a validação de completude por fatia
# deixa de funcionar. Fatia que passe disso é subdividida.
TETO_CONTAGEM_EXATA = 10_000

# Acima disso, a fatia residual é subdividida por @timestamp. Paginar
# dezenas de milhares numa sequência só faz o cluster percorrer cada vez
# mais do índice a cada página.
LIMITE_FATIA = 20_000

# @timestamp é a data de indexação no Datajud, instituído em 2020 pela
# Resolução CNJ 331. Faixas anteriores viriam vazias.
ANO_INICIAL_TIMESTAMP = 2020

# Anos do fatiamento. 2005 é o piso observado numa varredura dos 27 TJs
# (agregação por faixa de dataAjuizamento sobre o assunto 12091): há
# acervo anterior ao Datajud, carregado pelos tribunais na migração.
#
# Registros fora dessa faixa existem e são muitos -- 49% do TJSP, 40% do
# TJRJ, 39% do TJAC --, com dataAjuizamento presente mas fora de qualquer
# ano plausível. A fatia residual os captura; alargar a faixa não
# resolveria, porque o valor é inválido, não antigo.
ANO_INICIAL = 2005
ANOS = list(range(ANO_INICIAL, datetime.now().year + 1))

# Justiça estadual: é onde tramitam feminicídio e medida protetiva.
# Trabalhista, eleitoral e federal ficam de fora do recorte.
TRIBUNAIS_ESTADUAIS = [
    "tjac", "tjal", "tjam", "tjap", "tjba", "tjce", "tjdft", "tjes",
    "tjgo", "tjma", "tjmg", "tjms", "tjmt", "tjpa", "tjpb", "tjpe",
    "tjpi", "tjpr", "tjrj", "tjrn", "tjro", "tjrr", "tjrs", "tjsc",
    "tjse", "tjsp", "tjto",
]

# Campos da capa. Movimentos ficam de fora: são dezenas por processo e
# multiplicariam o volume -- viram fonte separada se a análise de
# tramitação for necessária.
CAMPOS = [
    "id", "tribunal", "numeroProcesso", "dataAjuizamento", "grau",
    "nivelSigilo", "classe", "assuntos", "orgaoJulgador", "formato",
    "dataHoraUltimaAtualizacao",
]


# Ordenação da paginação. Precisa ser estável e ÚNICA entre páginas:
# sem desempate único, search_after pula ou repete registros que
# compartilham o mesmo valor de data.
#
# _id não serve como desempate -- o cluster do CNJ tem
# indices.id_field_data.enabled desativado e devolve
# "Fielddata access on the _id field is disallowed". numeroProcesso é
# único por processo e agregável pelo subcampo .keyword.
#
# As duas últimas opções, sem desempate, são último recurso: funcionam,
# mas podem perder registros com data repetida.
ORDENACOES = [
    [{"@timestamp": {"order": "asc"}}, {"numeroProcesso.keyword": {"order": "asc"}}],
    [{"dataHoraUltimaAtualizacao": {"order": "asc"}},
     {"numeroProcesso.keyword": {"order": "asc"}}],
    [{"dataAjuizamento": {"order": "asc"}},
     {"numeroProcesso.keyword": {"order": "asc"}}],
    [{"numeroProcesso.keyword": {"order": "asc"}}],
    [{"@timestamp": {"order": "asc"}}],
    [{"dataAjuizamento": {"order": "asc"}}],
]

# Preenchido na primeira consulta bem-sucedida de cada tribunal. Cada
# thread escreve só a própria chave, mas o lock evita corrida na
# escrita do dict.
_ordenacao_valida: dict[str, list] = {}
_lock_ordenacao = threading.Lock()


def _chave_checkpoint(recorte: str) -> str:
    return f"{PASTA_BUCKET}/_checkpoint_{recorte}.json"


def carregar_checkpoint(recorte: str) -> dict:
    """Estado da extração por tribunal: search_after e total já baixado.

    Vive no bucket, não no disco: landing é scratch e sofre limpeza, e o
    checkpoint precisa sobreviver entre sessões.
    """
    s3 = get_s3_client()
    try:
        resposta = s3.get_object(
            Bucket=env_comum.MINIO_BUCKET, Key=_chave_checkpoint(recorte)
        )
        return json.loads(resposta["Body"].read())
    except Exception:
        return {}


# O checkpoint é um arquivo só no bucket, e com tribunais em paralelo
# várias threads o salvam ao mesmo tempo -- sem lock, uma sobrescreve o
# progresso da outra e a rodada seguinte rebaixa o que já veio.
_lock_checkpoint = threading.Lock()


def salvar_checkpoint(recorte: str, estado: dict):
    s3 = get_s3_client()
    with _lock_checkpoint:
        s3.put_object(
            Bucket=env_comum.MINIO_BUCKET,
            Key=_chave_checkpoint(recorte),
            Body=json.dumps(estado, indent=2, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )


def _espera_retry(tentativa: int) -> float:
    """Espera curta com jitter, crescendo devagar até um teto baixo.

    O jitter evita que retentativas simultâneas (vários tribunais, ou
    outros consumidores da API) batam no cluster no mesmo instante.
    """
    base = min(ESPERA_RETRY * (1 + tentativa * 0.5), ESPERA_MAXIMA)
    return base + random.uniform(0, 3)


def _consultar(tribunal: str, corpo: dict) -> dict | None:
    """POST com retry. Devolve None quando esgota as tentativas.

    429 (rate limit) e 504 (timeout do gateway) são esperados e tratados
    com espera crescente. 401 significa chave trocada pelo CNJ -- aborta,
    porque insistir não resolve.
    """
    url = f"{URL_BASE}/api_publica_{tribunal}/_search"
    cabecalho = {
        "Authorization": f"APIKey {API_KEY}",
        "Content-Type": "application/json",
    }

    for tentativa in range(MAX_TENTATIVAS):
        try:
            r = requests.post(url, headers=cabecalho, json=corpo, timeout=300)
            if r.status_code == 200:
                dados = r.json()
                # HTTP 200 não garante resposta completa: sob carga o
                # Elasticsearch responde com parte dos shards e sinaliza
                # em _shards.failed. Nesse caso tanto hits.total quanto os
                # próprios registros vêm truncados, e o search_after
                # avançaria por cima do buraco -- perda silenciosa.
                shards = dados.get("_shards", {})
                falhos = shards.get("failed", 0)
                if falhos:
                    logger.warning(
                        f"[{tribunal}] {falhos}/{shards.get('total')} shards falharam "
                        f"-- resposta parcial descartada "
                        f"(tentativa {tentativa + 1}/{MAX_TENTATIVAS})"
                    )
                    time.sleep(_espera_retry(tentativa))
                    continue
                return dados
            if r.status_code == 400:
                # Query malformada: repetir não resolve, e o corpo da
                # resposta traz o motivo -- sem ele o diagnóstico vira
                # adivinhação.
                logger.error(f"[{tribunal}] 400 -- query rejeitada: {r.text[:600]}")
                return None
            if r.status_code == 401:
                logger.error(
                    "401: a chave pública foi trocada pelo CNJ. Atualize API_KEY "
                    "a partir de https://datajud-wiki.cnj.jus.br/api-publica/acesso"
                )
                return None
            if r.status_code == 404:
                logger.warning(f"[{tribunal}] 404 -- alias inexistente, pulando.")
                return None
            logger.warning(
                f"[{tribunal}] HTTP {r.status_code} (tentativa {tentativa + 1}/{MAX_TENTATIVAS})"
            )
        except requests.RequestException as e:
            logger.warning(
                f"[{tribunal}] {type(e).__name__} (tentativa {tentativa + 1}/{MAX_TENTATIVAS})"
            )

        time.sleep(_espera_retry(tentativa))

    logger.error(f"[{tribunal}] esgotou as tentativas.")
    return None


def _corpo_busca(codigos: list[int], apos: list | None, ordenacao: list,
                 fatia: str | None = None, residual: bool = False,
                 cobertas: list[str] | None = None,
                 filtro_extra: dict | None = None) -> dict:
    """Query paginada por search_after, opcionalmente restrita a um período.

    from/size trava em 10.000 no Elasticsearch; search_after não tem teto.

    NAO_MULHER é excluído explicitamente: são casos em que a vítima não é
    mulher, e o assunto pode aparecer junto de um código do recorte.

    `fatia` é um prefixo de dataAjuizamento: '2024' pega o ano inteiro,
    '202403' só março. O filtro por período existe para manter a
    paginação rasa -- paginar dezenas de milhares numa sequência só faz o
    cluster percorrer cada vez mais do índice a cada página, e a taxa de
    rejeição cresce junto.

    A comparação é de STRING, não de data: dataAjuizamento é keyword e
    chega em três formatos ('20150729093223', '2016-07-15T...' e epoch).
    Os dois primeiros começam pelo ano, então ordenam lexicograficamente.

    residual=True inverte: pega o que não caiu em nenhuma fatia coberta --
    data em formato divergente, ausente ou fora do intervalo.
    """
    filtros = [{"terms": {"assuntos.codigo": codigos}}]
    excluir = [{"terms": {"assuntos.codigo": list(NAO_MULHER)}}]

    if residual:
        for f in (cobertas if cobertas is not None else [str(a) for a in ANOS]):
            excluir.append({"range": {"dataAjuizamento": _intervalo(f)}})
    elif fatia is not None:
        filtros.append({"range": {"dataAjuizamento": _intervalo(fatia)}})

    # Subdivisão do residual por @timestamp, quando ele é grande demais
    # para uma sequência só de search_after.
    if filtro_extra is not None:
        filtros.append(filtro_extra)

    corpo = {
        "size": TAMANHO_PAGINA,
        "_source": CAMPOS,
        "query": {"bool": {"filter": filtros, "must_not": excluir}},
        "sort": ordenacao,
        # Sem isso hits.total para em 10.000 e vira "gte", e a validação
        # de completude da fatia deixa de funcionar em tribunal grande.
        "track_total_hits": True,
    }
    if apos:
        corpo["search_after"] = apos
    return corpo


def _intervalo(fatia: str) -> dict:
    """Faixa [inicio, fim) para um prefixo de ano ('2024') ou mês ('202403')."""
    if len(fatia) == 4:
        return {"gte": fatia, "lt": str(int(fatia) + 1)}
    ano, mes = int(fatia[:4]), int(fatia[4:])
    if mes == 12:
        return {"gte": fatia, "lt": f"{ano + 1}01"}
    return {"gte": fatia, "lt": f"{ano}{mes + 1:02d}"}


def _meses(ano: int) -> list[str]:
    return [f"{ano}{m:02d}" for m in range(1, 13)]

    corpo = {
        "size": TAMANHO_PAGINA,
        "_source": CAMPOS,
        "query": {"bool": {"filter": filtros, "must_not": excluir}},
        "sort": ordenacao,
        # Sem isso hits.total para em 10.000 e vira "gte", e a validação
        # de completude da fatia deixa de funcionar em tribunal grande.
        "track_total_hits": True,
    }
    if apos:
        corpo["search_after"] = apos
    return corpo


def _descobrir_ordenacao(tribunal: str, codigos: list[int]) -> list | None:
    """Primeira ordenação que o índice aceita.

    Testada com size=1 para ser barata. Sem isso, um sort inválido só
    apareceria como 400 no meio da paginação.

    _consultar já distingue os casos: 400 (sort inválido) devolve None
    imediatamente, enquanto 429/504 são retentados internamente. Então um
    None aqui significa mesmo que a ordenação não serve -- e não que a
    API estava ocupada no momento.
    """
    if tribunal in _ordenacao_valida:
        return _ordenacao_valida[tribunal]

    for ordenacao in ORDENACOES:
        corpo = _corpo_busca(codigos, None, ordenacao)
        corpo["size"] = 1
        if _consultar(tribunal, corpo) is not None:
            campo = list(ordenacao[0])[0]
            desempate = list(ordenacao[1])[0] if len(ordenacao) > 1 else "sem desempate"
            logger.info(f"[{tribunal}] ordenação aceita: {campo} + {desempate}")
            if len(ordenacao) == 1:
                logger.warning(
                    f"[{tribunal}] ordenação sem desempate único: registros com "
                    f"a mesma data podem ser perdidos ou repetidos na paginação."
                )
            with _lock_ordenacao:
                _ordenacao_valida[tribunal] = ordenacao
            return ordenacao
        time.sleep(PAUSA_ENTRE_PAGINAS)

    logger.error(f"[{tribunal}] nenhuma ordenação aceita -- pulando tribunal.")
    return None


def _baixar_fatia(tribunal: str, codigos: list[int], fatia: str | None,
                  ordenacao: list, destino, chave: str, recorte: str,
                  estado: dict, info: dict, residual: bool = False,
                  cobertas: list[str] | None = None,
                  filtro_extra: dict | None = None) -> tuple[bool, int]:
    """Pagina uma fatia (ano, mês ou o residual). Devolve (ok, novos)."""
    estado_fatia = info.get("fatias", {}).get(chave, {})
    if estado_fatia.get("concluido"):
        return True, 0

    apos = estado_fatia.get("search_after")
    baixados = estado_fatia.get("baixados", 0)
    if apos:
        logger.info(f"[{tribunal}/{chave}] retomando de {baixados}.")

    novos = 0
    esperado = None

    def registrar(concluido: bool):
        info.setdefault("fatias", {})[chave] = {
            "search_after": apos, "baixados": baixados, "concluido": concluido,
        }
        estado[tribunal] = info
        salvar_checkpoint(recorte, estado)

    while True:
        resposta = _consultar(
            tribunal,
            _corpo_busca(codigos, apos, ordenacao, fatia, residual,
                         cobertas, filtro_extra),
        )
        if resposta is None:
            registrar(False)
            return False, novos

        # A contagem é relida a cada página e mantém-se a MAIOR observada.
        # Ficar com a primeira arriscaria validar contra um número baixo:
        # no TJGO a primeira página declarou 1.152 de um total de 2.359,
        # porque veio de uma resposta com shards rejeitados.
        # relation="gte" significa que passou do teto de contagem exata
        # (10.000) e o número real só se conhece ao terminar de paginar.
        total = resposta.get("hits", {}).get("total", {})
        if total.get("relation") == "eq":
            valor = total.get("value")
            if valor is not None and (esperado is None or valor > esperado):
                if esperado is not None:
                    logger.warning(
                        f"[{tribunal}/{chave}] total revisado de {esperado} para {valor}."
                    )
                esperado = valor

        hits = resposta.get("hits", {}).get("hits", [])
        if not hits:
            break

        with open(destino, "a", encoding="utf-8") as f:
            for h in hits:
                f.write(json.dumps(h["_source"], ensure_ascii=False) + "\n")

        apos = hits[-1]["sort"]
        baixados += len(hits)
        novos += len(hits)
        logger.info(f"[{tribunal}/{chave}] {baixados}"
                    + (f"/{esperado}" if esperado else "") + " registros...")
        registrar(False)

        # Não encerrar por `len(hits) < TAMANHO_PAGINA`: sob carga o
        # Elasticsearch devolve página parcial ao rejeitar shards, e ler
        # isso como fim perde o resto em silêncio -- foi o que cortou o
        # TJGO em 1.377 de 2.359. Só a página vazia encerra de verdade.
        time.sleep(PAUSA_ENTRE_PAGINAS)

    if esperado is not None and baixados < esperado:
        logger.error(
            f"[{tribunal}/{chave}] baixados {baixados} de {esperado} -- incompleto."
        )
        registrar(False)
        return False, novos

    registrar(True)
    return True, novos


def _contar_fatias(tribunal: str, codigos: list[int],
                   fatias: list[str]) -> dict[str, int] | None:
    """Contagem por fatia, via agregação. None se a agregação falhar."""
    corpo = {
        "size": 0,
        "query": {"bool": {
            "filter": [{"terms": {"assuntos.codigo": codigos}}],
            "must_not": [{"terms": {"assuntos.codigo": list(NAO_MULHER)}}],
        }},
        "aggs": {"fatias": {"range": {
            "field": "dataAjuizamento",
            "ranges": [
                {"key": f, "from": _intervalo(f)["gte"], "to": _intervalo(f)["lt"]}
                for f in fatias
            ],
        }}},
    }
    resposta = _consultar(tribunal, corpo)
    if resposta is None:
        return None
    baldes = resposta.get("aggregations", {}).get("fatias", {}).get("buckets")
    if baldes is None:
        return None
    return {b["key"]: b.get("doc_count", 0) for b in baldes}


def _descobrir_fatias(tribunal: str, codigos: list[int]) -> list[str] | None:
    """Fatias a paginar, no menor grão que cada período exigir.

    Duas armadilhas do Datajud moldam esta função:

    1. A contagem exata do Elasticsearch para em 10.000 (relation="gte").
       Sem track_total_hits, tribunal grande vira contagem cega.
    2. A agregação por período degrada em silêncio sob volume -- no TJMG,
       com 149 mil registros, reportou 2 fatias com dado e o resto zerado.
       Não dá erro; devolve zeros.

    Daí o desenho: a agregação orienta, mas nunca decide sozinha. O total
    do tribunal (consulta barata e confiável) valida o que ela diz, e o
    grão desce para mês SÓ nos anos que concentram volume -- aplicar
    mensal aos 22 anos daria 264 consultas, a maioria vazia, quando o
    acervo se concentra nos anos recentes.
    """
    total = _total_declarado(tribunal, codigos, exato=False)
    if total is None:
        return None

    if total < TETO_CONTAGEM_EXATA:
        logger.info(f"[{tribunal}] {total} registros -- sem fatiamento.")
        return [str(a) for a in ANOS]

    por_ano = _contar_fatias(tribunal, codigos, [str(a) for a in ANOS])

    # Agregação inútil (falhou, ou reportou tão pouco que não comporta o
    # total): fatia por ano em toda a faixa, cego. Mais consultas que o
    # necessário, mas nenhuma fatia gigante.
    soma = sum(por_ano.values()) if por_ano else 0
    if not por_ano or soma < total / 2:
        logger.warning(
            f"[{tribunal}] agregação por ano não confere com o total "
            f"({soma} de {total}) -- fatiando por ano, sem descartar vazios."
        )
        return [str(a) for a in ANOS]

    fatias: list[str] = []
    subdivididos = 0
    for ano in sorted(por_ano):
        qtd = por_ano[ano]
        if qtd == 0:
            continue
        if qtd < TETO_CONTAGEM_EXATA:
            fatias.append(ano)
            continue
        # Ano concentra volume: desce para mês. Só aqui -- é o que evita
        # as 264 consultas mensais em anos que têm dezenas de registros.
        por_mes = _contar_fatias(tribunal, codigos, _meses(int(ano)))
        if por_mes and sum(por_mes.values()) >= qtd / 2:
            fatias.extend(m for m in sorted(por_mes) if por_mes[m])
        else:
            fatias.extend(_meses(int(ano)))
        subdivididos += 1
        time.sleep(PAUSA_ENTRE_PAGINAS)

    logger.info(
        f"[{tribunal}] {total}+ registros em {len(fatias)} fatia(s)"
        + (f", {subdivididos} ano(s) subdividido(s) em meses." if subdivididos
           else ".")
    )
    return fatias or [str(a) for a in ANOS]


def _fatias_residuais(tribunal: str, codigos: list[int], cobertas: list[str],
                      ordenacao: list) -> list[tuple[str, dict | None]]:
    """Divide o residual em faixas de @timestamp quando ele for grande.

    O residual concentra tudo que dataAjuizamento não classifica -- e na
    prática isso é quase toda a base, porque o filtro por ano casa pouco.
    No TJMG do recorte violencia_genero foram 149 mil registros numa
    sequência única de search_after, com a paginação ficando mais lenta a
    cada página.

    @timestamp é gerado pelo CNJ na indexação, não pelo tribunal: está
    sempre presente e é ordenável de verdade, ao contrário de
    dataAjuizamento. Serve para partir o residual em blocos menores.

    Devolve [(chave, filtro_extra)]. filtro_extra None = residual
    inteiro, sem subdivisão.
    """
    corpo = {
        "size": 0,
        "track_total_hits": True,
        "query": {"bool": {
            "filter": [{"terms": {"assuntos.codigo": codigos}}],
            "must_not": ([{"terms": {"assuntos.codigo": list(NAO_MULHER)}}]
                         + [{"range": {"dataAjuizamento": _intervalo(f)}}
                            for f in cobertas]),
        }},
    }
    resposta = _consultar(tribunal, corpo)
    total = (resposta or {}).get("hits", {}).get("total", {}).get("value")
    if total is None or total < LIMITE_FATIA:
        return [("residual", None)]

    anos = list(range(ANO_INICIAL_TIMESTAMP, datetime.now().year + 1))
    logger.info(
        f"[{tribunal}] residual com {total} registros -- dividido em "
        f"{len(anos)} faixa(s) de @timestamp."
    )
    return [
        (f"residual_{a}", {"range": {"@timestamp": {
            "gte": f"{a}-01-01T00:00:00Z", "lt": f"{a + 1}-01-01T00:00:00Z",
        }}})
        for a in anos
    ]


def baixar_tribunal(tribunal: str, codigos: list[int], recorte: str,
                    estado: dict, anos: list[int] | None = None) -> tuple[bool, int]:
    """Baixa um tribunal, fatiando por ano de ajuizamento.

    O fatiamento mantém a paginação rasa: cada ano tem poucas centenas de
    registros, em vez de milhares numa única sequência de search_after
    cada vez mais profunda -- que é o que fazia a taxa de rejeição do
    cluster crescer página após página.

    Devolve (concluiu, novos). NDJSON em append: uma queda no meio não
    perde o que já veio, e o checkpoint retoma por fatia.
    """
    info = estado.get(tribunal, {})
    if info.get("concluido"):
        logger.info(f"[{tribunal}] já concluído nesta extração, pulando.")
        return True, 0

    destino = OUTPUT_DIR / recorte / f"{tribunal}.ndjson"
    destino.parent.mkdir(parents=True, exist_ok=True)

    ordenacao = _descobrir_ordenacao(tribunal, codigos)
    if ordenacao is None:
        return False, 0

    # Fatias por período, mais a residual: registros com dataAjuizamento
    # em formato divergente, ausente ou fora da faixa não caem em nenhum
    # período, e sem a residual sumiriam. Não é caso de borda -- no TJAC
    # a residual trouxe 150 dos 245, mais que todos os anos somados.
    if anos is None:
        descobertas = _descobrir_fatias(tribunal, codigos)
        if descobertas is None:
            descobertas = [str(a) for a in ANOS]

        # Se o grão mudou desde a última rodada, o checkpoint tem fatias
        # de um esquema e o código calcula outro: as antigas nunca seriam
        # concluídas e as novas rebaixariam o que já veio, duplicando no
        # NDJSON. Avisa em vez de misturar em silêncio.
        registradas = {
            k for k in info.get("fatias", {}) if not k.startswith("residual")
        }
        novas = set(descobertas)
        if registradas and not registradas <= novas:
            logger.error(
                f"[{tribunal}] o fatiamento mudou desde a última rodada "
                f"({len(registradas)} fatia(s) no checkpoint, {len(novas)} "
                f"calculada(s)). Rode com --reset neste tribunal para "
                f"refazer com o esquema novo."
            )
            return False, 0

        fatias = [(f, f, False, None) for f in descobertas]
        cobertas_ = [f for f in descobertas]
        for chave, extra in _fatias_residuais(
            tribunal, codigos, cobertas_, ordenacao
        ):
            fatias.append((None, chave, True, extra))
    else:
        fatias = [(str(a), str(a), False, None) for a in anos]

    novos = 0
    tudo_ok = True

    cobertas = [f for f, _, r, _e in fatias if not r and f is not None]
    for fatia, chave, residual, extra in fatias:
        ok, n = _baixar_fatia(tribunal, codigos, fatia, ordenacao, destino,
                              chave, recorte, estado, info, residual,
                              cobertas, extra)
        novos += n
        tudo_ok = tudo_ok and ok

    if tudo_ok:
        total = sum(f.get("baixados", 0) for f in info.get("fatias", {}).values())
        # Conferência final contra a contagem que a API declara para o
        # recorte inteiro. Foi essa comparação que revelou a paginação
        # truncada e os registros fora da faixa de anos -- os dois
        # passavam sem erro nenhum.
        # Só na carga completa: no incremental apenas algumas fatias são
        # reconsultadas e a soma naturalmente não bate com o total.
        # exato=False usa track_total_hits, que devolve a contagem real
        # mesmo acima de 10.000 -- sem isso a conferência de completude
        # não funcionava nos tribunais grandes, justamente onde mais
        # importa.
        declarado = _total_declarado(tribunal, codigos, exato=False) if anos is None else None
        if declarado is not None and total != declarado:
            logger.error(
                f"[{tribunal}] baixados {total}, API declara {declarado} "
                f"-- divergência de {abs(declarado - total)}. NÃO marcado como "
                f"concluído; rode de novo para retomar."
            )
            estado[tribunal] = info
            salvar_checkpoint(recorte, estado)
            return False, novos

        info["concluido"] = True
        estado[tribunal] = info
        salvar_checkpoint(recorte, estado)
        logger.info(f"[{tribunal}] concluído: {total} registros.")
    return tudo_ok, novos


def _total_declarado(tribunal: str, codigos: list[int],
                     exato: bool = True) -> int | None:
    """Contagem que a API informa para o recorte inteiro, sem paginar.

    exato=True devolve None quando a contagem vem truncada no teto de
    10.000 (relation="gte"), porque aí não serve para conferir
    completude. exato=False devolve o valor mesmo truncado, que é o
    suficiente para dimensionar o grão do fatiamento.
    """
    corpo = {
        "size": 0,
        "query": {"bool": {
            "filter": [{"terms": {"assuntos.codigo": codigos}}],
            "must_not": [{"terms": {"assuntos.codigo": list(NAO_MULHER)}}],
        }},
    }
    if not exato:
        # track_total_hits remove o teto de 10.000 e devolve a contagem
        # real -- mais caro, mas é uma consulta por tribunal.
        corpo["track_total_hits"] = True

    resposta = _consultar(tribunal, corpo)
    if resposta is None:
        return None
    total = resposta.get("hits", {}).get("total", {})
    if exato and total.get("relation") != "eq":
        return None
    return total.get("value")


def resetar(recorte: str, tribunais: list[str], estado: dict):
    """Limpa checkpoint e NDJSON dos tribunais indicados.

    Necessário depois de corrigir um bug de extração: sem isso o tribunal
    fica marcado como concluído e é pulado, e o NDJSON antigo continuaria
    no disco, misturando dado velho com novo no append.
    """
    for tribunal in tribunais:
        estado.pop(tribunal, None)
        arquivo = OUTPUT_DIR / recorte / f"{tribunal}.ndjson"
        if arquivo.exists():
            arquivo.unlink()
            logger.info(f"[{tribunal}] NDJSON apagado.")
    salvar_checkpoint(recorte, estado)
    logger.info(f"Checkpoint limpo para: {', '.join(tribunais)}")


def main(argv: list[str]) -> int:
    global PARALELISMO
    reset = "--reset" in argv
    incremental = "--incremental" in argv
    for a in argv:
        if a.startswith("--paralelismo="):
            PARALELISMO = max(1, int(a.split("=", 1)[1]))
    argv = [a for a in argv if not a.startswith("--")]

    recorte = argv[0] if argv else "feminicidio"
    if recorte not in RECORTES:
        logger.error(f"Recorte '{recorte}' inválido. Use: {', '.join(RECORTES)}")
        return exit_codes.ERRO

    tribunais = argv[1].split(",") if len(argv) > 1 else TRIBUNAIS_ESTADUAIS
    codigos = RECORTES[recorte]

    logger.info(
        f"Recorte '{recorte}': assuntos {codigos} em {len(tribunais)} tribunal(is)."
    )

    estado = carregar_checkpoint(recorte)
    if reset:
        resetar(recorte, tribunais, estado)

    anos = None
    if incremental:
        # Só o ano corrente e o anterior: processo novo entra no ano
        # atual, e revisão de processo recente ainda pode chegar. Anos
        # antigos não mudam o bastante para justificar reconsulta.
        #
        # As fatias desses anos são reabertas para que o search_after
        # salvo continue de onde parou, trazendo só o que entrou depois.
        anos = [datetime.now().year - 1, datetime.now().year]
        logger.info(f"Modo incremental: reconsultando {anos}.")
        for tribunal in tribunais:
            info = estado.get(tribunal, {})
            info.pop("concluido", None)
            for ano in anos:
                fatia = info.get("fatias", {}).get(str(ano))
                if fatia:
                    fatia["concluido"] = False
            estado[tribunal] = info

    total_novos = 0
    houve_falha = False

    if PARALELISMO > 1 and len(tribunais) > 1:
        # Cada tribunal é um índice diferente no Elasticsearch, então
        # rodar vários em paralelo não disputa o mesmo shard. Os 429 que
        # a API devolve são de fila do cluster, não throttling por
        # cliente -- por isso o paralelismo ajuda em vez de piorar.
        logger.info(f"Extraindo {PARALELISMO} tribunais em paralelo.")
        with ThreadPoolExecutor(max_workers=PARALELISMO) as pool:
            futuros = {
                pool.submit(baixar_tribunal, t, codigos, recorte, estado, anos): t
                for t in tribunais
            }
            for futuro in as_completed(futuros):
                tribunal = futuros[futuro]
                try:
                    ok, novos = futuro.result()
                except Exception as e:
                    logger.error(f"[{tribunal}] {type(e).__name__}: {e}")
                    ok, novos = False, 0
                total_novos += novos
                houve_falha = houve_falha or not ok
    else:
        for tribunal in tribunais:
            ok, novos = baixar_tribunal(tribunal, codigos, recorte, estado, anos)
            total_novos += novos
            houve_falha = houve_falha or not ok

    if houve_falha:
        logger.warning(
            "Extração incompleta -- rode de novo para retomar do checkpoint."
        )
        return exit_codes.ERRO
    if total_novos == 0:
        logger.info("Nenhum registro novo.")
        return exit_codes.SEM_NOVIDADE
    logger.info(f"{total_novos} registros novos.")
    return exit_codes.SUCESSO


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))