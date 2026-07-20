import os
import re
import socket
import time
import random
import logging
from ftplib import FTP, error_perm
from typing import Callable

from scripts.common.bucket_sync import carregar_manifesto

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("datasus_ftp")

FTP_HOST = "ftp.datasus.gov.br"
MAX_RETRIES = 10
RETRY_DELAY = 5

# SOCKS5 opcional -- porta 21 costuma ser bloqueada em VPS/cloud.
# Rode: ssh -R 1080 -N usuario@IP_VPS
SOCKS5_PROXY_ENABLED = os.environ.get("SOCKS5_PROXY_ENABLED", "false").lower() in ("1", "true", "yes")
SOCKS5_PROXY_HOST = os.environ.get("SOCKS5_PROXY_HOST", "127.0.0.1")
SOCKS5_PROXY_PORT = int(os.environ.get("SOCKS5_PROXY_PORT", "1080"))

if SOCKS5_PROXY_ENABLED:
    import socks
    socks.set_default_proxy(socks.SOCKS5, SOCKS5_PROXY_HOST, SOCKS5_PROXY_PORT)
    socket.socket = socks.socksocket
    logger.info(f"[SOCKS5] Roteamento reverso ativado ({SOCKS5_PROXY_HOST}:{SOCKS5_PROXY_PORT}).")


class FTPPasvFix(FTP):
    """Ignora o IP devolvido na resposta 227 (comum estar errado atrás de
    NAT/load balancer) e usa o host da conexão de controle."""
    def makepasv(self):
        host, port = super().makepasv()
        host_real = self.sock.getpeername()[0]
        if host != host_real:
            logger.warning(f"[PASV] Servidor devolveu IP {host}, usando {host_real} em vez disso.")
        return host_real, port


def ensure_output_dir(path: str):
    os.makedirs(path, exist_ok=True)


def get_tamanho_ftp(ftp: FTP, nome_arquivo: str) -> int | None:
    try:
        return ftp.size(nome_arquivo)
    except error_perm:
        return None


def _backoff(attempt: int):
    """Backoff exponencial com jitter, evita retries sincronizados."""
    espera = min(RETRY_DELAY * (2 ** attempt), 120) + random.uniform(0, 3)
    logger.info(f"Aguardando {espera:.1f}s antes de tentar de novo...")
    time.sleep(espera)


def _chave_recencia(nome_arquivo: str) -> str:
    """Extrai os dígitos finais (competência) antes da extensão.

    Ordenar pelo nome inteiro seria errado: nomes começam pela UF
    (DOAC94, DOSP94...), então "os últimos N alfabeticamente" seriam
    dominados por UFs no fim do alfabeto, não pelas datas recentes.

    Ano de 2 dígitos é normalizado para 4 (mesma regra do filtro em
    fetch_sim_causas_externas: >= 90 é 19xx, senão 20xx). Sem isso
    DOEXT96..99 ordenam DEPOIS de DOEXT00..24, e a otimização acaba
    verificando os anos mais antigos achando que são os recentes.
    """
    m = re.search(r"(\d+)\.\w+$", nome_arquivo, re.IGNORECASE)
    if not m:
        return nome_arquivo

    digitos = m.group(1)
    if len(digitos) == 2:
        ano = int(digitos)
        return str(1900 + ano) if ano >= 90 else str(2000 + ano)
    return digitos


def _deduplicar_case(nomes: list[str]) -> list[str]:
    """Remove duplicatas por maiúscula/minúscula (X.DBC e X.dbc), mantendo a primeira."""
    vistos = set()
    resultado = []
    for nome in nomes:
        chave = nome.upper()
        if chave in vistos:
            continue
        vistos.add(chave)
        resultado.append(nome)
    return resultado


def baixar_arquivo(ftp_dir: str, nome_arquivo: str, pasta_saida: str,
                    manifesto: dict[str, int] | None = None) -> tuple[bool, bool]:
    """Retorna (sucesso, houve_novidade).

    houve_novidade=False se o arquivo já está completo localmente ou já
    consta no manifesto com o mesmo tamanho.
    """
    local_path = os.path.join(pasta_saida, nome_arquivo)
    tamanho_ftp = None

    for attempt in range(MAX_RETRIES):
        try:
            ip_v4 = socket.gethostbyname(FTP_HOST)
            logger.info(f"[{nome_arquivo}] Tentativa {attempt + 1}/{MAX_RETRIES} -- conectando em {ip_v4}")

            with FTPPasvFix() as ftp:
                ftp.connect(ip_v4, 21, timeout=30)
                ftp.login()
                ftp.set_pasv(True)
                ftp.cwd(ftp_dir)

                tamanho_ftp = get_tamanho_ftp(ftp, nome_arquivo)
                if not tamanho_ftp:
                    print(f"[ERRO] Não foi possível obter tamanho de {nome_arquivo}")
                    if attempt < MAX_RETRIES - 1:
                        _backoff(attempt)
                        continue
                    return False, False

                if manifesto is not None and manifesto.get(nome_arquivo.upper()) == tamanho_ftp:
                    print(f"[SKIP-MANIFESTO] {nome_arquivo} já incorporado ao último output publicado.")
                    return True, False

                tamanho_local = os.path.getsize(local_path) if os.path.exists(local_path) else 0

                if tamanho_local >= tamanho_ftp:
                    print(f"[SKIP] {nome_arquivo} (Completo: {tamanho_local} bytes)")
                    return True, False

                rest_pos = tamanho_local if tamanho_local > 0 else None
                modo_abertura = "ab" if tamanho_local > 0 else "wb"

                if rest_pos:
                    print(f"[RESUME] {nome_arquivo} do byte {rest_pos} (Tentativa {attempt + 1}/{MAX_RETRIES})")
                else:
                    print(f"[DOWN] {nome_arquivo} (Tentativa {attempt + 1}/{MAX_RETRIES})")

                with open(local_path, modo_abertura) as f:
                    ftp.sock.settimeout(300)
                    ftp.retrbinary(f"RETR {nome_arquivo}", f.write, rest=rest_pos, blocksize=32768)

                if os.path.getsize(local_path) == tamanho_ftp:
                    print(f"[OK] {nome_arquivo} concluído.")
                    return True, True
                else:
                    raise Exception("Download interrompido (tamanho incompleto)")

        except (socket.timeout, EOFError, ConnectionResetError, Exception) as e:
            logger.error(f"[{nome_arquivo}] Falha na tentativa {attempt + 1}: {type(e).__name__}: {e}")
            if attempt < MAX_RETRIES - 1:
                _backoff(attempt)
            else:
                print(f"[FATAL] Desistindo de {nome_arquivo} após {MAX_RETRIES} tentativas.")
                if os.path.exists(local_path) and os.path.getsize(local_path) < (tamanho_ftp or 0):
                    os.remove(local_path)
                return False, False
    return False, False


def sincronizar_ftp(ftp_dir: str, output_dir: str, regra_filtro: Callable[[str], bool],
                     pasta_bucket: str | None = None,
                     verificar_ultimas_n_competencias: int = 2) -> tuple[bool, bool]:
    """Retorna (sucesso, houve_novidade).

    pasta_bucket: carrega o manifesto dessa pasta UMA vez para decidir o
    que pular, em vez de um head_object por arquivo.

    verificar_ultimas_n_competencias: cada checagem de tamanho abre uma
    conexão FTP nova, o que fica caro em fontes com muitos arquivos. Como
    o DATASUS só revisa competências recentes, agrupa por competência (ver
    _chave_recencia) e verifica de fato apenas as N mais recentes -- todas
    as UFs delas. Arquivos fora do manifesto são sempre verificados.
    """
    ensure_output_dir(output_dir)
    logger.info(f"Conectando a {FTP_HOST} ({ftp_dir}) para listar arquivos...")
    relevantes = []

    manifesto = carregar_manifesto(pasta_bucket) if pasta_bucket else None

    for attempt in range(MAX_RETRIES):
        try:
            ip_v4 = socket.gethostbyname(FTP_HOST)
            with FTPPasvFix() as ftp:
                ftp.connect(ip_v4, 21, timeout=30)
                ftp.login()
                ftp.set_pasv(True)
                ftp.cwd(ftp_dir)

                ftp.sock.settimeout(60)
                arquivos = ftp.nlst()

                if not arquivos:
                    print("Nenhum arquivo encontrado no diretório.")
                    return True, False

                relevantes_brutos = [arq for arq in arquivos if regra_filtro(arq)]
                relevantes = _deduplicar_case(relevantes_brutos)
                duplicatas = len(relevantes_brutos) - len(relevantes)
                if duplicatas:
                    print(f"[AVISO] {duplicatas} duplicata(s) por maiúscula/minúscula removida(s).")

                print(f"Sucesso ao listar! {len(relevantes)} arquivos passaram no filtro.")
                break

        except Exception as e:
            logger.error(f"Falha ao listar diretório (Tentativa {attempt + 1}): {type(e).__name__}: {e}")
            if attempt == MAX_RETRIES - 1:
                print("[FATAL] Não foi possível listar os arquivos do FTP.")
                return False, False
            _backoff(attempt)

    if manifesto is not None and relevantes:
        competencias = sorted(set(_chave_recencia(a) for a in relevantes))
        recentes = set(competencias[-verificar_ultimas_n_competencias:])

        a_verificar = []
        pulados = 0
        for arq in relevantes:
            if _chave_recencia(arq) in recentes or arq.upper() not in manifesto:
                a_verificar.append(arq)
            else:
                pulados += 1

        if pulados:
            print(f"[OTIMIZAÇÃO] {pulados} arquivo(s) de competência antiga já no manifesto -- "
                  f"pulando verificação de rede (só as {verificar_ultimas_n_competencias} "
                  f"competências mais recentes + novos são checados).")
        relevantes = a_verificar

    sucesso_geral = True
    houve_novidade = False
    for arq in relevantes:
        sucesso, novidade = baixar_arquivo(ftp_dir, arq, output_dir, manifesto=manifesto)
        sucesso_geral = sucesso_geral and sucesso
        houve_novidade = houve_novidade or novidade

    if houve_novidade:
        print("[INFO] Sincronização concluída com novos arquivos.")
    else:
        print("[INFO] Sincronização concluída. Nenhuma atualização necessária.")

    return sucesso_geral, houve_novidade