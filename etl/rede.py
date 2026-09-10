"""
etl/rede.py
Acesso de rede às fontes oficiais, com as retentativas e o TLS que cada host exige.

As duas fontes deste projeto publicam ZIPs grandes dos quais precisamos de
poucos membros. Em vez de baixar tudo e descartar a maior parte, `ZipRemoto` lê
o índice do ZIP (que fica no FIM do arquivo) e depois só os intervalos de bytes
dos membros desejados. A mesma máquina serve aos dois, mudando só o transporte:

  · INEP (download.inep.gov.br) — HTTPS com Range
    O Censo 2024 tem 436 MB; os dois CSVs usados somam uma fração disso.
    Duas patologias medidas:
      - HEAD é derrubado com frequência (~1 em 3). Sondagem usa GET Range 0-0.
      - O certificado NÃO valida contra o bundle do certifi: o servidor não
        envia o intermediário e só completa a cadeia por AIA, que o certifi
        não busca. O truststore do sistema valida. Ver `_contexto_tls`.

  · DATASUS (ftp.datasus.gov.br) — FTP com REST
    A base mensal do CNES tem 700 MB. O host não atende HTTP algum:
    `arquivos.datasus.gov.br` não resolve e `ftp.datasus.gov.br` recusa 80/443.
    Derruba ~2 de 3 conexões que usam REST, então retentativa não é otimização,
    é requisito — sem ela a leitura falha quase sempre e a falha se disfarça
    de "arquivo indisponível".

O contrato de sondagem é de TRÊS estados, nunca dois:
    (True,  detalhe)  publicado
    (False, detalhe)  confirmadamente ausente
    (None,  detalhe)  indeterminado — não foi possível verificar

Tratar indeterminado como "sem novidade" silencia o alerta de frescor. Esse
erro regrediu duas vezes no projeto de Farmácia; aqui ele é difícil de cometer
por acidente porque `sondar` nunca devolve booleano puro.
"""
import io
import json
import socket
import ssl
import struct
import sys
import time
import urllib.error
import urllib.request
import zlib
from ftplib import FTP
from pathlib import Path

TENTATIVAS_HTTP = 4
TENTATIVAS_FTP = 12          # ~2 de 3 conexões REST caem; 12 dá margem folgada
ESPERA_BASE = 4
UA = "observatorio-psicologia/1.0 (+https://github.com/esidiao)"

_CTX = None


def _contexto_tls():
    """
    Contexto TLS que valida a cadeia do INEP.

    `requests` usa o bundle do certifi, que não valida download.inep.gov.br:
    o servidor apresenta um certificado válido (*.inep.gov.br) mas não envia o
    certificado intermediário, e a cadeia só fecha buscando-o por AIA. O
    truststore do sistema faz essa busca; o certifi, não.

    A correção é usar o truststore do sistema — NUNCA desligar a verificação.
    Um observatório que se apoia em proveniência não pode baixar dado oficial
    por canal não autenticado; seria contradizer o próprio princípio.
    """
    global _CTX
    if _CTX is None:
        ctx = ssl.create_default_context()
        ctx.load_default_certs(ssl.Purpose.SERVER_AUTH)
        _CTX = ctx
    return _CTX


def _abrir(url, headers=None, timeout=120):
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    return urllib.request.urlopen(req, timeout=timeout, context=_contexto_tls())


def ler_json(url, tentativas=TENTATIVAS_HTTP, timeout=120):
    """
    Baixa e decodifica JSON, com retentativa.

    Descomprime gzip por conta própria: a API de localidades do IBGE responde
    com Content-Encoding: gzip mesmo sem o cliente pedir, e `urllib` — ao
    contrário de `requests` — não descomprime sozinha. Sem isto, a resposta
    chega como bytes que estouram em UnicodeDecodeError no segundo byte, e o
    erro parece corrupção de rede em vez de compressão não tratada.
    """
    import gzip
    import zlib as _zlib

    ultimo = ""
    for tentativa in range(tentativas):
        try:
            r = _abrir(url, {"Accept": "application/json"}, timeout=timeout)
            bruto = r.read()
            codificacao = (r.headers.get("Content-Encoding") or "").lower()
            r.close()
            if codificacao == "gzip" or bruto[:2] == b"\x1f\x8b":
                bruto = gzip.decompress(bruto)
            elif codificacao == "deflate":
                bruto = _zlib.decompress(bruto)
            return json.loads(bruto.decode("utf-8"))
        except Exception as e:                                 # noqa: BLE001
            ultimo = f"{type(e).__name__}: {e}"
        if tentativa < tentativas - 1:
            time.sleep(ESPERA_BASE * (tentativa + 1))
    raise RuntimeError(f"não foi possível ler {url}: {ultimo}")


# --------------------------------------------------------------------------- #
# Sondagem de frescor
# --------------------------------------------------------------------------- #

def sondar(url, tentativas=TENTATIVAS_HTTP, espera=ESPERA_BASE):
    """Devolve (existe, detalhe) com existe em {True, False, None}."""
    ultimo = ""
    for tentativa in range(tentativas):
        try:
            r = _abrir(url, {"Range": "bytes=0-0"}, timeout=40)
            codigo = r.status
            r.close()
            if codigo in (200, 206):
                return True, str(codigo)
            ultimo = f"HTTP {codigo}"
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False, "404"
            if e.code in (200, 206, 416):
                return True, str(e.code)
            ultimo = f"HTTP {e.code}"
        except Exception as e:                                 # noqa: BLE001
            ultimo = type(e).__name__
        if tentativa < tentativas - 1:
            time.sleep(espera)
    return None, ultimo


def tamanho_remoto(url, tentativas=TENTATIVAS_HTTP):
    """
    Tamanho em bytes, lido do Content-Range de um GET Range 0-0.

    Levanta em vez de devolver None em falha de rede. A primeira versão desta
    função engolia a exceção e devolvia None, e quem chamava traduzia isso para
    "servidor sem suporte a Range" — que é uma afirmação sobre o servidor,
    baseada em nenhuma evidência. É o mesmo erro que `sondar` existe para
    evitar: indeterminado não é ausente, e a distinção precisa sobreviver à
    borda de cada função, não só à do relatório.
    """
    ultimo = ""
    for tentativa in range(tentativas):
        try:
            r = _abrir(url, {"Range": "bytes=0-0"}, timeout=60)
            cr = r.headers.get("Content-Range", "")
            codigo = r.status
            r.close()
            if "/" in cr:
                total = cr.rsplit("/", 1)[-1]
                if total.isdigit():
                    return int(total)
            raise RuntimeError(
                f"{url} respondeu {codigo} sem Content-Range — "
                "servidor não suporta leitura por intervalo")
        except RuntimeError:
            raise
        except Exception as e:                                 # noqa: BLE001
            ultimo = f"{type(e).__name__}: {e}"
        if tentativa < tentativas - 1:
            time.sleep(ESPERA_BASE * (tentativa + 1))
    raise RuntimeError(f"não foi possível medir {url}: {ultimo}")


# --------------------------------------------------------------------------- #
# ZIP remoto — leitura de membros isolados
# --------------------------------------------------------------------------- #

class _FluxoBlocos(io.RawIOBase):
    """Adapta um gerador de blocos de bytes a um objeto legível em fluxo."""

    def __init__(self, gerador):
        self._gerador = gerador
        self._buffer = b""
        self._fim = False

    def readable(self):
        return True

    def readinto(self, destino):
        while not self._buffer and not self._fim:
            try:
                self._buffer = next(self._gerador)
            except StopIteration:
                self._fim = True
        n = min(len(destino), len(self._buffer))
        destino[:n] = self._buffer[:n]
        self._buffer = self._buffer[n:]
        return n


class ZipRemoto:
    """
    Base: sabe interpretar um ZIP a partir de leituras por intervalo de bytes.

    Não usa `zipfile` porque `zipfile` exige um objeto seekable com o arquivo
    inteiro disponível; aqui o "seek" é a própria requisição de rede.

    Subclasses implementam apenas `tamanho()` e `_ler(inicio, quantidade)`.
    """

    CAUDA = 120_000       # cauda baixada para achar EOCD + índice

    def __init__(self):
        self._indice = None
        self._tamanho = None

    # -- a implementar ------------------------------------------------------

    def tamanho(self):
        raise NotImplementedError

    def _ler(self, inicio, quantidade):
        raise NotImplementedError

    # -- índice -------------------------------------------------------------

    def indice(self):
        """{nome_do_membro: {csz, usz, meth, lho}} — lido do central directory."""
        if self._indice is not None:
            return self._indice

        tamanho = self.tamanho()
        cauda_n = min(self.CAUDA, tamanho)
        base = tamanho - cauda_n
        cauda = self._ler(base, cauda_n)

        i = cauda.rfind(b"PK\x05\x06")
        if i < 0:
            raise RuntimeError("EOCD não encontrado — aumentar ZipRemoto.CAUDA")
        cd_tam = struct.unpack("<I", cauda[i + 12:i + 16])[0]
        cd_off = struct.unpack("<I", cauda[i + 16:i + 20])[0]

        inicio_rel = cd_off - base
        cd = (cauda[inicio_rel:inicio_rel + cd_tam] if inicio_rel >= 0
              else self._ler(cd_off, cd_tam))

        membros, p = {}, 0
        while p < len(cd) and cd[p:p + 4] == b"PK\x01\x02":
            nl, el, cl = struct.unpack("<HHH", cd[p + 28:p + 34])
            csz, usz = struct.unpack("<II", cd[p + 20:p + 28])
            flag = struct.unpack("<H", cd[p + 8:p + 10])[0]
            meth = struct.unpack("<H", cd[p + 10:p + 12])[0]
            lho = struct.unpack("<I", cd[p + 42:p + 46])[0]
            # Bit 11 do general purpose flag declara nome em UTF-8. Os ZIPs do
            # INEP marcam; os do DATASUS, não. Decodificar sempre em latin-1
            # transforma "Dicionário" em "DicionÃ¡rio" e faz `localizar` errar.
            nome = cd[p + 46:p + 46 + nl].decode(
                "utf-8" if flag & 0x800 else "latin-1", "replace")
            membros[nome] = {"csz": csz, "usz": usz, "meth": meth, "lho": lho}
            p += 46 + nl + el + cl

        if not membros:
            raise RuntimeError("central directory vazio ou ilegível")
        self._indice = membros
        return membros

    def localizar(self, *padroes):
        """
        Devolve o nome do primeiro membro que contém TODOS os padrões (sem
        distinguir maiúsculas), ou None.

        Existe porque o diretório interno dos ZIPs do INEP muda de nome e de
        acentuação a cada edição. Localizar por padrão evita caminho fixo, que
        quebra silenciosamente na virada de ano.
        """
        alvos = [p.lower() for p in padroes]
        for nome in sorted(self.indice()):
            baixo = nome.lower()
            if all(a in baixo for a in alvos):
                return nome
        return None

    # -- extração -----------------------------------------------------------

    def _inicio_dados(self, alvo):
        idx = self.indice()
        if alvo not in idx:
            raise KeyError(f"{alvo} não está no arquivo remoto")
        m = idx[alvo]
        # O cabeçalho local repete nome e extra com tamanhos PRÓPRIOS; o campo
        # `extra` costuma diferir do registrado no central directory, então ele
        # é lido do próprio cabeçalho em vez de reaproveitado do índice.
        lh = self._ler(m["lho"], 30)
        nl, el = struct.unpack("<HH", lh[26:30])
        return m["lho"] + 30 + nl + el, m

    def membro_blocos(self, alvo, bloco=1 << 23):
        """
        Gera os bytes descomprimidos de um membro, em blocos.

        Necessário, não conveniente: o cadastro de cursos do Censo tem 432 MB e
        a carga horária do CNES tem 834 MB descomprimidos. Materializar
        qualquer um dos dois inteiro na memória é o caminho mais curto para um
        MemoryError no runner do CI, que tem 7 GB para tudo.
        """
        inicio, m = self._inicio_dados(alvo)
        restante = m["csz"]
        desc = zlib.decompressobj(-15) if m["meth"] == 8 else None
        pos = inicio
        while restante > 0:
            n = min(bloco, restante)
            bruto = self._ler(pos, n)
            pos += n
            restante -= n
            yield desc.decompress(bruto) if desc else bruto
        if desc:
            resto = desc.flush()
            if resto:
                yield resto

    def membro(self, alvo):
        """Bytes descomprimidos de um membro, inteiro. Só para membros pequenos."""
        return b"".join(self.membro_blocos(alvo))

    def membro_texto(self, alvo, encoding="latin-1"):
        return self.membro(alvo).decode(encoding, "replace")

    def membro_arquivo(self, alvo, encoding="latin-1", bloco=1 << 23):
        """
        Objeto de texto em fluxo, pronto para `csv.DictReader`.

        Devolver um TextIOWrapper em vez de um gerador de linhas é deliberado:
        o `csv` precisa enxergar as quebras de linha originais para reconstruir
        campos entre aspas que contêm quebra. Um gerador que já removeu o "\\n"
        corrompe esses campos sem emitir erro.
        """
        return io.TextIOWrapper(
            _FluxoBlocos(self.membro_blocos(alvo, bloco)),
            encoding=encoding, errors="replace", newline="")

    def extrair_para(self, alvo, destino):
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(self.membro(alvo))
        return destino


class ZipRemotoHTTP(ZipRemoto):
    """ZIP lido por requisições Range. Usado no INEP."""

    def __init__(self, url, tentativas=TENTATIVAS_HTTP):
        super().__init__()
        self.url = url
        self.tentativas = tentativas

    def tamanho(self):
        if self._tamanho is None:
            self._tamanho = tamanho_remoto(self.url, self.tentativas)
        return self._tamanho

    def _ler(self, inicio, quantidade):
        fim = inicio + quantidade - 1
        ultimo = ""
        for tentativa in range(self.tentativas):
            try:
                r = _abrir(self.url, {"Range": f"bytes={inicio}-{fim}"}, timeout=300)
                dados = r.read()
                r.close()
                if len(dados) == quantidade:
                    return dados
                ultimo = f"leitura curta ({len(dados)}/{quantidade})"
            except Exception as e:                             # noqa: BLE001
                ultimo = type(e).__name__
            if tentativa < self.tentativas - 1:
                time.sleep(ESPERA_BASE * (tentativa + 1))
        raise RuntimeError(f"falha ao ler {self.url} em {inicio}+{quantidade}: {ultimo}")


class ZipRemotoFTP(ZipRemoto):
    """ZIP lido por RETR com REST. Usado no DATASUS."""

    def __init__(self, host, diretorio, nome, timeout=300,
                 tentativas=TENTATIVAS_FTP):
        super().__init__()
        self.host = host
        self.diretorio = diretorio
        self.nome = nome
        self.timeout = timeout
        self.tentativas = tentativas
        socket.setdefaulttimeout(timeout)

    def _conectar(self):
        f = FTP(self.host, timeout=self.timeout)
        f.login()
        f.cwd(self.diretorio)
        f.voidcmd("TYPE I")
        return f

    def listar_diretorio(self):
        """Nomes de arquivo no diretório remoto, com retentativa."""
        ultimo = ""
        for tentativa in range(self.tentativas):
            try:
                f = self._conectar()
                nomes = f.nlst()
                f.quit()
                return nomes
            except Exception as e:                             # noqa: BLE001
                ultimo = type(e).__name__
                time.sleep(2)
        raise RuntimeError(f"falha ao listar {self.host}{self.diretorio}: {ultimo}")

    def tamanho(self):
        if self._tamanho is None:
            ultimo = ""
            for _ in range(self.tentativas):
                try:
                    f = self._conectar()
                    self._tamanho = f.size(self.nome)
                    f.quit()
                    break
                except Exception as e:                         # noqa: BLE001
                    ultimo = type(e).__name__
                    time.sleep(2)
            if self._tamanho is None:
                raise RuntimeError(
                    f"não foi possível obter o tamanho de {self.nome}: {ultimo}")
        return self._tamanho

    def _ler(self, inicio, quantidade):
        ultimo = ""
        for tentativa in range(self.tentativas):
            try:
                f = self._conectar()
                conn = f.transfercmd(f"RETR {self.nome}", rest=inicio)
                buf = bytearray()
                while len(buf) < quantidade:
                    bloco = conn.recv(1 << 16)
                    if not bloco:
                        break
                    buf += bloco
                conn.close()
                # `close()`, não `quit()`. Quase toda leitura aqui é PARCIAL:
                # pedimos RETR do arquivo inteiro a partir de um offset e
                # fechamos assim que os bytes pedidos chegam, com o servidor
                # ainda enviando. `quit()` mandaria QUIT e esperaria resposta
                # de um servidor ocupado despejando o resto de um arquivo de
                # 700 MB — e travaria até o timeout de 300 s a cada bloco.
                # `close()` derruba o socket de controle sem diálogo.
                f.close()
                if len(buf) >= quantidade:
                    return bytes(buf[:quantidade])
                ultimo = f"leitura curta ({len(buf)}/{quantidade})"
            except Exception as e:                             # noqa: BLE001
                ultimo = type(e).__name__
            if tentativa < self.tentativas - 1:
                time.sleep(min(2 * (tentativa + 1), 15))
        raise RuntimeError(
            f"falha ao ler {self.nome} em {inicio}+{quantidade}: {ultimo}")


# --------------------------------------------------------------------------- #
# Download completo, com retentativa
# --------------------------------------------------------------------------- #

def baixar(url, destino, tentativas=4, timeout=900):
    """
    Baixa um arquivo inteiro, refazendo do zero a cada falha.

    Não retoma por Range: um ZIP truncado que parece completo custa mais caro
    que um download refeito, e confiar no Range do servidor para retomada é
    exatamente o tipo de suposição que este projeto evita. (Ler intervalos
    isolados, como faz ZipRemotoHTTP, é outra coisa: lá o tamanho esperado é
    conhecido e conferido a cada leitura.)
    """
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)

    for tentativa in range(1, tentativas + 1):
        marca = "" if tentativa == 1 else f" (tentativa {tentativa}/{tentativas})"
        print(f"[GET] {url}{marca}")
        try:
            r = _abrir(url, timeout=timeout)
            baixado = 0
            with open(destino, "wb") as saida:
                while True:
                    bloco = r.read(1 << 20)
                    if not bloco:
                        break
                    saida.write(bloco)
                    baixado += len(bloco)
                    print(f"\r      {baixado / 1048576:.0f} MB", end="", flush=True)
            r.close()
            print()
            return destino
        except Exception as e:                                 # noqa: BLE001
            print(f"\n[AVISO] {type(e).__name__}: {e}", file=sys.stderr)
            destino.unlink(missing_ok=True)
            if tentativa == tentativas:
                raise
            time.sleep(5 * 2 ** (tentativa - 1))
