"""Extração Datajud (CNJ) -- Metadados processuais (limitados a capa/movimentos, sem partes).

Estratégia de extração devido à instabilidade da API (HTTP 429/504, teto de 10k):
- Checkpoint via bucket para extração idempotente e retomável.
- Fatiamento dinâmico (por data de ajuizamento) para forçar paginação rasa (shallow pagination) 
  e reduzir rejeição de shards no cluster Elasticsearch do CNJ.

Uso:
    python -m scripts.extract.datajud.fetch_datajud_violencia [recorte] [tribunais] [flags]
    Flags: --reset, --incremental, --paralelismo=N
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

# Chave pública (Wiki CNJ). Em caso de HTTP 401, buscar a vigente 
# em https://datajud-wiki.cnj.jus.br/api-publica/acesso.
API_KEY = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="

# Persiste em MANUAL_DIR (e não LANDING_DIR efêmero) como backup bruto 
# devido ao alto custo computacional da extração.
OUTPUT_DIR = MANUAL_DIR / "datajud"
PASTA_BUCKET = "datajud"

# Teto da API é 10k. 2.000 é o trade-off que minimiza idas 
# (10-30s cada) sem forçar alta rejeição de shards.
TAMANHO_PAGINA = 2_000

PAUSA_ENTRE_PAGINAS = 2

# Rejeição de API (429) reflete fila de cluster, não rate-limit por cliente. 
# Backoff curto + jitter é mais eficaz.
MAX_TENTATIVAS = 15
ESPERA_RETRY = 4
ESPERA_MAXIMA = 20

# Paralelismo conservador (cada tribunal é um índice isolado, mas a fila do 
# ES é compartilhada).
PARALELISMO = 4

# Limite hardcoded do Elasticsearch (hits.total.relation="gte" acima de 10k). 
# Fatias excedentes sofrem subdivisão.
TETO_CONTAGEM_EXATA = 10_000

# Teto para evitar deep pagination. A fatia residual é subdividida por 
# @timestamp caso passe deste valor.
LIMITE_FATIA = 20_000

# Data de indexação via Resolução CNJ 331. Documentos anteriores não possuem 
# este metadata confiável.
ANO_INICIAL_TIMESTAMP = 2020

# 2005 é o piso empírico migrado. Registros inválidos ou anômalos de data (comuns) 
# vão intencionalmente para a fatia residual.
ANO_INICIAL = 2005
ANOS = list(range(ANO_INICIAL, datetime.now().year + 1))


TRIBUNAIS_ESTADUAIS = [
    "tjac", "tjal", "tjam", "tjap", "tjba", "tjce", "tjdft", "tjes",
    "tjgo", "tjma", "tjmg", "tjms", "tjmt", "tjpa", "tjpb", "tjpe",
    "tjpi", "tjpr", "tjrj", "tjrn", "tjro", "tjrr", "tjrs", "tjsc",
    "tjse", "tjsp", "tjto",
]

# Exclui movimentos (tramitações) para evitar explosão exponencial do payload.
CAMPOS = [
    "id", "tribunal", "numeroProcesso", "dataAjuizamento", "grau",
    "nivelSigilo", "classe", "assuntos", "orgaoJulgador", "formato",
    "dataHoraUltimaAtualizacao",
]


# Ordenações com desempate determinístico (numeroProcesso.keyword). 
# _id não pode ser usado (CNJ bloqueia fielddata). Ordenações sem 
# desempate causam perdas/duplicatas na paginação.
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

_ordenacao_valida: dict[str, list] = {}
_lock_ordenacao = threading.Lock()


def _chave_checkpoint(recorte: str) -> str:
    return f"{PASTA_BUCKET}/_checkpoint_{recorte}.json"


def carregar_checkpoint(recorte: str) -> dict:
    """Retorna estado da extração (search_after e totais baixados). Persiste no S3/MinIO 
    para proteção contra expurgo de disco."""
    s3 = get_s3_client()
    try:
        resposta = s3.get_object(
            Bucket=env_comum.MINIO_BUCKET, Key=_chave_checkpoint(recorte)
        )
        return json.loads(resposta["Body"].read())
    except Exception:
        return {}


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
    base = min(ESPERA_RETRY * (1 + tentativa * 0.5), ESPERA_MAXIMA)
    return base + random.uniform(0, 3)


def _consultar(tribunal: str, corpo: dict) -> dict | None:
    """POST com backoff. Devolve None ao esgotar tentativas ou encontrar 
    HTTP 400/401 (falha irrecuperável)."""
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
                # Alerta Elasticsearch: HTTP 200 sob carga pode retornar sucesso parcial 
                # (_shards.failed). 
                # Requer descarte e retry para evitar falha silenciosa de search_after.
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
    """Constrói payload ES (search_after e range).
    
    Técnica: `dataAjuizamento` requer comparação lexicográfica estrita (tipo keyword misturando formatos).
    Fatiamento restringe o cursor, forçando shallow pagination (mitiga timeout).
    `residual=True` captura o esgoto lógico (inconsistências que escapam ao regex temporal base).
    """
    filtros = [{"terms": {"assuntos.codigo": codigos}}]
    excluir = [{"terms": {"assuntos.codigo": list(NAO_MULHER)}}]

    if residual:
        for f in (cobertas if cobertas is not None else [str(a) for a in ANOS]):
            excluir.append({"range": {"dataAjuizamento": _intervalo(f)}})
    elif fatia is not None:
        filtros.append({"range": {"dataAjuizamento": _intervalo(fatia)}})


    if filtro_extra is not None:
        filtros.append(filtro_extra)

    corpo = {
        "size": TAMANHO_PAGINA,
        "_source": CAMPOS,
        "query": {"bool": {"filter": filtros, "must_not": excluir}},
        "sort": ordenacao,
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
    """Probe (size=1) para descobrir o sort de índice suportado (TJs não possuem schema rígido)."""
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

        # Fix/ES: hits.total subnotifica se o cluster dropar parcialidades. 
        # Matém o teto alto (HWM) já visto.
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

        # Terminador estrito: Só encerra em len == 0 (len < TAMANHO_PAGINA é normal 
        # via timeout de shard).
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
    """Calcula malha de fatiamento (mensal vs anual).
    Fallback contra bug do Datajud onde agregações de alto volume retornam zeros (falha silenciosa).
    Desce para a granularidade mensal exclusivamente em anos que esbarram nos limites do ES.
    """
    total = _total_declarado(tribunal, codigos, exato=False)
    if total is None:
        return None

    if total < TETO_CONTAGEM_EXATA:
        logger.info(f"[{tribunal}] {total} registros -- sem fatiamento.")
        return [str(a) for a in ANOS]

    por_ano = _contar_fatias(tribunal, codigos, [str(a) for a in ANOS])

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
        # Drill-down: fragmenta em meses unicamente onde o ano concentra volume.
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
    """Subdivide a fatia residual ancorada em `@timestamp`.
    Impede deep pagination nos casos onde o `dataAjuizamento` não ajuda (maior parte da base legada).
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
    """Orquestra a extração persistindo em NDJSON via append mode para viabilizar checkpoint per-chunk."""
    info = estado.get(tribunal, {})
    if info.get("concluido"):
        logger.info(f"[{tribunal}] já concluído nesta extração, pulando.")
        return True, 0

    destino = OUTPUT_DIR / recorte / f"{tribunal}.ndjson"
    destino.parent.mkdir(parents=True, exist_ok=True)

    ordenacao = _descobrir_ordenacao(tribunal, codigos)
    if ordenacao is None:
        return False, 0

    if anos is None:
        descobertas = _descobrir_fatias(tribunal, codigos)
        if descobertas is None:
            descobertas = [str(a) for a in ANOS]

        # Bloqueio arquitetural: Aborta se detectar alteração do schema 
        # de fatias para evitar perdas/duplicatas.
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
        # Asserção de completude (ignorada em incrementais). Necessita de track_total_hits 
        # bypassando o limite de 10k.
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
    """Extrai hits.total da query base. `exato=False` aciona flag `track_total_hits=True`."""
    corpo = {
        "size": 0,
        "query": {"bool": {
            "filter": [{"terms": {"assuntos.codigo": codigos}}],
            "must_not": [{"terms": {"assuntos.codigo": list(NAO_MULHER)}}],
        }},
    }
    if not exato:
        corpo["track_total_hits"] = True

    resposta = _consultar(tribunal, corpo)
    if resposta is None:
        return None
    total = resposta.get("hits", {}).get("total", {})
    if exato and total.get("relation") != "eq":
        return None
    return total.get("value")


def resetar(recorte: str, tribunais: list[str], estado: dict):
    """Evita poluição e duplicação resetando checkpoints em bucket e logs em disco."""
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
        # Delta mode: zera completion status das fatias dos últimos dois anos.
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