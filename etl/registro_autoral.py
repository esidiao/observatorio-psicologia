"""
etl/registro_autoral.py
Registro de anterioridade autoral: resumo criptográfico de cada arquivo
autoral, com a data em que foi calculado.

Uso:
    python etl/registro_autoral.py
    python etl/registro_autoral.py --verificar

Saída: data/registro_autoral.json

O QUE ISTO É — E O QUE NÃO É
-----------------------------
É uma declaração datada de quais arquivos existiam, com que conteúdo exato, na
data do registro. Serve para comparar uma cópia com o original e mostrar o que
mudou, arquivo por arquivo.

NÃO é registro em cartório, não é depósito no INPI e não constitui prova
oponível a terceiros por si só. Dizer o contrário seria vender ao leitor uma
garantia que este arquivo não tem — e um projeto que se recusa a inventar
número não deveria inventar garantia jurídica.

O QUE ENTRA
-----------
Só o que é autoral: código, textos, templates e o desenho dos índices. Ficam de
fora os dados públicos (que são do INEP, do DATASUS e do IBGE, não deste
projeto) e as bibliotecas de terceiros em `site/static/vendor` e
`site/static/fonts`. Registrar o dado alheio como obra própria seria o oposto
do que este arquivo existe para fazer.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SAIDA = REPO / "data" / "registro_autoral.json"

AUTOR = {
    "nome": "Edson Sidião de Souza Júnior",
    "contato": "sidiao@i9educar.com",
    "lattes": "http://lattes.cnpq.br/9464330669014306",
    "vinculo": "I9 Educar — Consultoria em Gestão Educacional",
    "qualificacao": (
        "Farmacêutico (UFG), Mestre e Doutor em Medicina Tropical (UFG); "
        "avaliador ad hoc do INEP/MEC há mais de quinze anos e avaliador do "
        "Conselho Estadual de Educação de Goiás."
    ),
    "obra": "Observatório Nacional da Formação em Psicologia",
    "descricao": (
        "Sítio estático data-driven com indicadores de acesso territorial, "
        "qualidade e cobertura assistencial dos cursos de Psicologia no "
        "Brasil: formulação e cálculo dos índices ICT, E, IAF, ICAP, ICRP e "
        "ICAS, catálogo de indicadores, textos e desenho editorial."
    ),
}

FUNDAMENTO = (
    "Lei 9.610/1998 (direitos autorais) e Lei 9.609/1998 (programa de "
    "computador). O resumo combinado é impressão digital única do conjunto; o "
    "commit Git ancora a data no histórico versionado."
)

COMO_VERIFICAR = [
    "1. Obtenha os arquivos listados em 'arquivos'.",
    "2. Normalize o fim de linha de cada um para LF.",
    "3. Calcule o SHA-256 de cada arquivo normalizado e compare com o campo "
    "'sha256' da respectiva entrada.",
    "4. Para o conjunto: concatene, na ordem em que aparecem em 'arquivos', o "
    "caminho seguido do seu resumo, sem separador, e calcule o SHA-256 do "
    "resultado. Deve ser igual a 'sha256_combinado'.",
    "5. Ou, direto: rode `python etl/registro_autoral.py --verificar`.",
    "6. O commit indicado em 'git_commit_ancora' comprova a data no histórico "
    "do repositório.",
]


def _commit_ancora():
    """
    Commit do HEAD, para ancorar a data do registro no histórico.

    Devolve None fora de um repositório git — o registro continua válido como
    declaração datada, só perde a âncora. Inventar um identificador aqui seria
    pior que não ter nenhum.
    """
    import subprocess
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(REPO),
                           capture_output=True, text=True)
        return r.stdout.strip() or None if r.returncode == 0 else None
    except Exception:                                          # noqa: BLE001
        return None

# Diretórios e padrões varridos, na ordem em que aparecem no registro.
PADROES = [
    "README.md",
    "SECURITY.md",
    "DIREITOS.md",
    "requirements.txt",
    "etl/*.py",
    "site/*.py",
    "site/templates/*.j2",
    "site/static/css/*.css",
    "site/static/js/app.js",
    "tests/*.py",
    ".github/workflows/*.yml",
]

EXCLUIR = ("site/static/vendor", "site/static/fonts", "etl/dados",
           "site/dist", "__pycache__")


def _normalizar(conteudo):
    """
    Bytes com fim de linha normalizado em LF, antes de resumir.

    O registro precisa identificar CONTEÚDO, não a tradução de fim de linha da
    máquina que o gerou. Sem isto ele só confere no sistema em que nasceu: o
    Windows grava CRLF nos arquivos escritos em modo texto, o git guarda LF no
    blob, e o mesmo arquivo produz dois resumos diferentes conforme onde é
    lido. Foi o que aconteceu — o registro batia local e acusava doze arquivos
    alterados no runner Linux do CI, sem que uma linha tivesse mudado.

    Um registro de anterioridade que só confere na máquina do autor não serve
    para nada: a razão de existir é permitir que OUTRA pessoa, em OUTRO
    sistema, compare a cópia dela com o original.
    """
    return conteudo.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _autorais():
    vistos = set()
    for padrao in PADROES:
        for caminho in sorted(REPO.glob(padrao)):
            relativo = caminho.relative_to(REPO).as_posix()
            if any(x in relativo for x in EXCLUIR):
                continue
            if not caminho.is_file() or relativo in vistos:
                continue
            vistos.add(relativo)
            yield relativo, caminho


def gerar():
    arquivos = []
    combinado = hashlib.sha256()
    for relativo, caminho in _autorais():
        conteudo = _normalizar(caminho.read_bytes())
        resumo = hashlib.sha256(conteudo).hexdigest()
        # A cadeia combinada inclui o CAMINHO, não só o conteúdo: sem isso,
        # renomear dois arquivos entre si daria o mesmo resumo global, e o
        # registro não perceberia a troca.
        combinado.update(relativo.encode("utf-8"))
        combinado.update(resumo.encode("ascii"))
        arquivos.append({
            "arquivo": relativo,
            "bytes": len(conteudo),
            "linhas": conteudo.count(b"\n") + 1,
            "sha256": resumo,
        })

    return {
        "autor": AUTOR,
        "registrado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit_ancora": _commit_ancora(),
        "algoritmo": "SHA-256 sobre o conteúdo com fim de linha normalizado em LF",
        "fundamento": FUNDAMENTO,
        "como_verificar": COMO_VERIFICAR,
        "natureza": (
            "Declaração datada de conteúdo, com anterioridade ancorada no "
            "histórico do repositório. Permite comparar uma cópia com o "
            "original arquivo a arquivo. Não é registro em cartório nem "
            "depósito no INPI, e não substitui nenhum dos dois."
        ),
        "escopo": (
            "Apenas material autoral: código, textos, templates e o desenho "
            "dos índices. Não inclui os dados públicos (INEP, DATASUS, IBGE), "
            "que pertencem às respectivas fontes, nem bibliotecas de terceiros."
        ),
        "n_arquivos": len(arquivos),
        "bytes_totais": sum(a["bytes"] for a in arquivos),
        "sha256_combinado": combinado.hexdigest(),
        "arquivos": arquivos,
    }


def verificar():
    """Compara o estado atual com o registro gravado. Devolve código de saída."""
    if not SAIDA.exists():
        print("[REGISTRO] nenhum registro gravado; rode sem --verificar.")
        return 1
    anterior = json.loads(SAIDA.read_text(encoding="utf-8"))
    atual = gerar()

    antes = {a["arquivo"]: a["sha256"] for a in anterior["arquivos"]}
    agora = {a["arquivo"]: a["sha256"] for a in atual["arquivos"]}

    novos = sorted(set(agora) - set(antes))
    removidos = sorted(set(antes) - set(agora))
    alterados = sorted(a for a in set(antes) & set(agora) if antes[a] != agora[a])

    print(f"[REGISTRO] registrado em {anterior['registrado_em']}")
    print(f"[REGISTRO] {len(anterior['arquivos'])} arquivos no registro, "
          f"{len(atual['arquivos'])} agora")
    for rotulo, lista in (("novo", novos), ("removido", removidos),
                          ("alterado", alterados)):
        for arquivo in lista:
            print(f"  {rotulo:9} {arquivo}")

    if not (novos or removidos or alterados):
        print("[REGISTRO] idêntico ao registro gravado.")
        return 0
    print("[REGISTRO] há diferenças — regrave o registro se forem intencionais.")
    return 1


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--verificar", action="store_true",
                   help="compara o estado atual com o registro, sem regravar")
    args = p.parse_args()

    if args.verificar:
        raise SystemExit(verificar())

    registro = gerar()
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(registro, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    print(f"[REGISTRO] {registro['n_arquivos']} arquivos, "
          f"{registro['bytes_totais']} bytes")
    print(f"[REGISTRO] sha256 combinado: {registro['sha256_combinado']}")
    print(f"[REGISTRO] -> {SAIDA}")


if __name__ == "__main__":
    main()
