"""
tests/test_links.py
Todo link e todo recurso do site gerado tem de existir no que é publicado.

Existe por um defeito concreto, encontrado no observatório de Odontologia só
DEPOIS de publicar: o gerador escrevia a planilha com o nome de um projeto
irmão enquanto o template linkava o nome certo. O download estava quebrado em
todas as páginas do site, e nada acusou — o build passou, os testes passaram e
a página continuou bonita. Um 404 não reprova build nenhum.

São dois sentidos, e os dois importam:

  · link sem arquivo — o leitor clica e recebe 404;
  · arquivo sem link — a planilha é gerada, ninguém a alcança, e o nome errado
    do outro lado passa despercebido. Foi esta metade que denunciou o defeito.

A verificação é feita contra o SISTEMA DE ARQUIVOS gerado, não contra a rede:
roda offline, no CI, antes de publicar. Links externos (http, mailto) ficam de
fora de propósito — quebram por motivo alheio ao repositório, e um teste que
falha por causa de terceiro é um teste que se aprende a ignorar.

Case-sensitive por opção: o GitHub Pages serve de um sistema de arquivos que
distingue maiúsculas, e o Windows, onde estes projetos são desenvolvidos, não.
Sem comparar caixa, `municipio/GO/goiania.html` passaria na máquina do autor e
daria 404 no ar.

Pulado quando `site/dist` não existe — rode `python site/build.py` antes.
"""
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

REPO = Path(__file__).resolve().parent.parent
DIST = REPO / "site" / "dist"

PADRAO = re.compile(r'(?:href|src)\s*=\s*"([^"]+)"', re.I)
EXTERNOS = ("http://", "https://", "//", "mailto:", "tel:", "data:",
            "javascript:", "#")

# Extensões cujo único caminho até o leitor é um link numa página. JSON e
# GeoJSON ficam de fora: são buscados por JavaScript em tempo de execução, e
# cobrá-los aqui produziria falha onde não há defeito.
BAIXAVEIS = (".xlsx", ".csv", ".pdf", ".zip")


def _paginas():
    return sorted(DIST.rglob("*.html")) if DIST.exists() else []


# Listagem por diretório, lida uma vez. Sem o cache, cada link relistava a
# pasta inteira: no observatório de Educação Superior, com 10.121 páginas em
# poucos diretórios, isso virou varredura quadrática e queimou 400 s de CPU sem
# terminar. O teste que demora é o teste que alguém tira do CI.
_LISTAGENS: dict = {}


def _existe(caminho: Path) -> bool:
    """
    Existência sensível à caixa, mesmo em sistema de arquivos que não é.

    `Path.exists()` no Windows diz que `GOIANIA.html` e `goiania.html` são o
    mesmo arquivo. No Linux do GitHub Pages, não são — e é lá que o leitor
    recebe o 404. Comparar o nome contra a listagem real do diretório resolve
    as duas coisas de uma vez: confere existência e confere caixa.
    """
    pasta = caminho.parent
    nomes = _LISTAGENS.get(pasta)
    if nomes is None:
        try:
            nomes = {item.name for item in pasta.iterdir()}
        except OSError:
            nomes = set()
        _LISTAGENS[pasta] = nomes
    return caminho.name in nomes


_REFERENCIAS = None


def _referencias():
    """
    Devolve (pagina_relativa, alvo_bruto, destino_absoluto) de cada link.

    Links montados em tempo de execução ficam de fora: `href="uf/${sigla}.html"`
    dentro de uma template string de JavaScript não é um caminho, é um molde, e
    cobrá-lo contra o disco acusaria defeito onde não há. O caso vizinho recebe
    tratamento oposto: `{{ ... }}` que sobrou no HTML é Jinja que NÃO renderizou,
    e isso é defeito de verdade — segue como referência quebrada.
    """
    global _REFERENCIAS
    if _REFERENCIAS is not None:
        return _REFERENCIAS

    # Lista, não gerador: os dois testes percorrem as mesmas referências, e o
    # site do observatório de Educação Superior tem 323 MB em 10.121 páginas —
    # lê-las duas vezes dobrava um custo que já é o dominante.
    _REFERENCIAS = []
    for pagina in _paginas():
        html = pagina.read_text(encoding="utf-8", errors="replace")
        relativa = pagina.relative_to(DIST).as_posix()
        for alvo in PADRAO.findall(html):
            alvo = alvo.strip()
            if not alvo or alvo.startswith(EXTERNOS) or "${" in alvo:
                continue
            caminho = unquote(urlparse(alvo).path)
            if not caminho:
                continue
            destino = (DIST / caminho.lstrip("/") if caminho.startswith("/")
                       else pagina.parent / caminho)
            _REFERENCIAS.append((relativa, alvo, destino))
    return _REFERENCIAS


def test_todo_link_interno_aponta_para_arquivo_existente():
    if not _paginas():
        print("          (pulado: site/dist ausente — rode python site/build.py)")
        return

    quebrados = [(p, alvo) for p, alvo, destino in _referencias()
                 if not _existe(destino)]
    # Uma amostra basta para o diagnóstico: um nome de arquivo errado aparece em
    # todas as páginas de uma vez, e listar centenas de ocorrências do mesmo
    # defeito esconde os outros.
    alvos = sorted({alvo for _p, alvo in quebrados})
    assert not quebrados, (
        f"{len(quebrados)} referências quebradas, {len(alvos)} alvos "
        "distintos:\n  - " + "\n  - ".join(alvos[:15])
        + "\n\nExemplos: "
        + "; ".join(f"{p} -> {a}" for p, a in quebrados[:5]))


def test_nenhum_arquivo_baixavel_fica_orfao():
    """
    O sentido inverso: arquivo gerado que nenhuma página alcança.

    É a metade que pega o nome errado na origem. Quando o gerador escreve
    `dados/observatorio-<outro-projeto>.xlsx` e o template linka o nome certo,
    o teste de links quebrados acusa o link — e este acusa o arquivo largado,
    que é onde está a causa.
    """
    if not _paginas():
        print("          (pulado: site/dist ausente)")
        return

    alcancados = {destino.resolve() for _p, _a, destino in _referencias()
                  if _existe(destino)}
    orfaos = []
    for arquivo in sorted(DIST.rglob("*")):
        if arquivo.is_file() and arquivo.suffix.lower() in BAIXAVEIS:
            if arquivo.resolve() not in alcancados:
                orfaos.append(arquivo.relative_to(DIST).as_posix())

    assert not orfaos, (
        "arquivos gerados que nenhuma página referencia:\n  - "
        + "\n  - ".join(orfaos)
        + "\n\nOu falta o link, ou o nome do arquivo diverge do que as páginas "
          "pedem — nos dois casos o leitor não chega até ele.")


def main():
    testes = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    falhas = 0
    for teste in testes:
        try:
            teste()
            print(f"  OK      {teste.__name__}")
        except AssertionError as e:
            falhas += 1
            print(f"  FALHOU  {teste.__name__}: {e}")
    print(f"\n{len(testes) - falhas}/{len(testes)} testes de links passaram.")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
