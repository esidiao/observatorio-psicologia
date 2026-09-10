"""
etl/pipeline.py
Orquestrador: verifica fontes, extrai, calcula, confere e só então publica.

Uso:
    python etl/pipeline.py --check-only        # só verifica frescor das fontes
    python etl/pipeline.py --ano 2024          # pipeline completo
    python etl/pipeline.py --ano 2024 --pular-cnes

A ORDEM NÃO É NEGOCIÁVEL
------------------------
    extrair_censo -> ingestao -> extrair_cpc -> extrair_cnes -> extrair_suas
                                                             -> consolidar

`ingestao` produz `vagas_presencial` e `vagas_ead`; só depois disso faz sentido
`consolidar` calcular pct_ead, HHI sobre a capacidade total e o ICT. Invertido,
o consolidador grava `None` em cadeia sem reclamar de nada: o arquivo sai com as
chaves certas e os valores vazios, e nenhum teste de integridade repara, porque
as chaves existem.

A GUARDA DE RIQUEZA
-------------------
`conferir_riqueza()` compara o número de campos por UF com o que está em
`git show HEAD` e ABORTA se o resultado novo for mais pobre.

Ela existe por um caso concreto do observatório de Farmácia: republicar por um
caminho parcial derrubou 33 dos 51 campos por UF, com todos os testes verdes —
porque nenhum teste checava PRESENÇA de campo. O site continuou no ar, bonito,
com dois terços das páginas vazias, e ninguém notou por semanas.

TRÊS ESTADOS POR FONTE, NUNCA DOIS
-----------------------------------
publicada / confirmadamente ausente / indeterminado. Tratar falha de rede como
"sem novidade" silencia o alerta inteiro — no projeto de Farmácia isso regrediu
duas vezes. Aqui `rede.sondar` nunca devolve booleano puro, o que torna o erro
difícil de cometer por acidente.
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rede import sondar  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
ETL = REPO / "etl"
DATA = REPO / "data"

URL_CENSO = ("https://download.inep.gov.br/microdados/"
             "microdados_censo_da_educacao_superior_{ano}.zip")
# Duas grafias, porque o INEP não é consistente entre ciclos: 2023 publica
# `CPC_2023.xlsx` e 2022 publica `cpc_2022.xlsx`. Sondar só uma delas devolve
# 404 e faz o verificador concluir que o ciclo não existe.
URLS_CPC = [
    ("https://download.inep.gov.br/educacao_superior/indicadores/"
     "resultados/{ano}/CPC_{ano}.xlsx"),
    ("https://download.inep.gov.br/educacao_superior/indicadores/"
     "resultados/{ano}/cpc_{ano}.xlsx"),
]

# Fontes cuja publicação NÃO é verificável automaticamente hoje, com o motivo
# concreto. Ficam declaradas para que a limitação apareça no relatório semanal
# em vez de virar um silêncio que passa por "tudo em dia".
FONTES_SEM_SONDAGEM = {
    "e_mec": (
        "e-MEC não expõe API pública nem URL de arquivo estável; o portal é "
        "renderizado por JavaScript e não há endpoint documentado."
    ),
    "censo_suas_microdados": (
        "O catálogo de microdados da SAGI/MDS responde com aviso de "
        "indisponibilidade por restrição de período eleitoral, e o conjunto "
        "CadSUAS no Portal Brasileiro de Dados Abertos exige chave de API "
        "(401). A cobertura socioassistencial vem da API MI Social, que é "
        "pública mas não versiona edições — não há data de publicação a "
        "sondar, só o período mais recente, que o próprio extrator descobre. "
        "Quando o catálogo voltar, vale reavaliar se o microdado do Censo SUAS "
        "traz abertura por ocupação, que é o que falta hoje para contar "
        "psicólogos no SUAS."
    ),
}


def _github_output(chave, valor):
    caminho = os.environ.get("GITHUB_OUTPUT", "")
    if caminho:
        with open(caminho, "a", encoding="utf-8") as f:
            f.write(f"{chave}={valor}\n")


def _rodar(script, *args):
    comando = [sys.executable, str(ETL / script), *map(str, args)]
    print(f"\n[PIPELINE] $ {' '.join(comando[1:])}")
    resultado = subprocess.run(comando, cwd=str(ETL))
    if resultado.returncode != 0:
        raise SystemExit(f"[PIPELINE] {script} falhou "
                         f"(código {resultado.returncode}). Nada foi publicado.")


# --------------------------------------------------------------------------- #
# Verificação de frescor
# --------------------------------------------------------------------------- #

def _serie_anual(rotulo, url_padrao, ano_atual, ano_limite):
    """Procura edição mais recente que `ano_atual`. Devolve (novidades, indeterminados)."""
    novidades, indeterminados = [], []
    if not ano_atual:
        return novidades, ["{}: ano corrente desconhecido".format(rotulo)]
    for ano in range(int(ano_atual) + 1, ano_limite + 1):
        existe, detalhe = sondar(url_padrao.format(ano=ano))
        if existe:
            novidades.append(f"{rotulo} {ano}")
            print(f"[CHECK] NOVIDADE: {rotulo} {ano} publicado (atual: {ano_atual}).")
        elif existe is None:
            indeterminados.append(f"{rotulo} {ano} ({detalhe})")
            print(f"[CHECK] INDETERMINADO: {rotulo} {ano} não verificável ({detalhe}).")
        else:
            print(f"[CHECK] {rotulo} {ano}: confirmadamente não publicado (404).")
    return novidades, indeterminados


def _serie_anual_multi(rotulo, padroes, ano_atual, ano_limite):
    """
    Como `_serie_anual`, mas com VÁRIAS grafias possíveis por ano.

    Um ano só é declarado ausente quando TODAS as grafias devolvem 404
    confirmado. Se qualquer uma ficar indeterminada, o ano fica indeterminado —
    senão bastaria uma falha de rede numa das duas para o verificador afirmar
    que a edição não existe, que é exatamente a confusão entre indeterminado e
    ausente que este módulo existe para impedir.
    """
    novidades, indeterminados = [], []
    if not ano_atual:
        return novidades, [f"{rotulo}: ano corrente desconhecido"]
    for ano in range(int(ano_atual) + 1, ano_limite + 1):
        achou = False
        pendentes = []
        for padrao in padroes:
            existe, detalhe = sondar(padrao.format(ano=ano))
            if existe:
                achou = True
                break
            if existe is None:
                pendentes.append(detalhe)
        if achou:
            novidades.append(f"{rotulo} {ano}")
            print(f"[CHECK] NOVIDADE: {rotulo} {ano} publicado (atual: {ano_atual}).")
        elif pendentes:
            indeterminados.append(f"{rotulo} {ano} ({'; '.join(pendentes)})")
            print(f"[CHECK] INDETERMINADO: {rotulo} {ano} não verificável.")
        else:
            print(f"[CHECK] {rotulo} {ano}: confirmadamente não publicado (404) "
                  f"em todas as {len(padroes)} grafias conhecidas.")
    return novidades, indeterminados


def _competencia_cnes(competencia_atual):
    """
    Verifica o CNES pela COMPETÊNCIA disponível, não por Last-Modified.

    A base recebe um arquivo novo por mês, então qualquer cabeçalho de data
    muda sempre e dispararia alerta toda semana mesmo sem novidade útil. A
    pergunta certa é se existe competência mais recente que a extraída.
    """
    from rede import ZipRemotoFTP
    import re

    try:
        z = ZipRemotoFTP("ftp.datasus.gov.br", "/cnes", "irrelevante")
        nomes = z.listar_diretorio()
    except Exception as e:                                     # noqa: BLE001
        return [], [f"CNES ({type(e).__name__}) — não foi possível listar o FTP"]

    comps = sorted(
        m.group(1) for m in
        (re.match(r"BASE_DE_DADOS_CNES_(\d{6})\.ZIP$", n, re.I) for n in nomes)
        if m)
    if not comps:
        return [], ["CNES (nenhuma competência encontrada — layout mudou?)"]
    if not competencia_atual:
        return [], ["CNES (proveniência sem competência registrada)"]

    mais_novas = [c for c in comps if c > str(competencia_atual)]
    if mais_novas:
        print(f"[CHECK] NOVIDADE: CNES {mais_novas[-1]} disponível "
              f"(atual: {competencia_atual}).")
        return [f"CNES {mais_novas[-1]}"], []
    print(f"[CHECK] CNES: {competencia_atual} continua sendo a mais recente.")
    return [], []


def verificar_fontes():
    prov = {}
    caminho = DATA / "_proveniencia.json"
    if caminho.exists():
        prov = json.loads(caminho.read_text(encoding="utf-8")).get("fontes", {})

    ano_limite = date.today().year
    novidades, indeterminados = [], []

    ano_censo = (prov.get("censo") or {}).get("ano_censo")
    n, i = _serie_anual("Censo da Educação Superior", URL_CENSO, ano_censo, ano_limite)
    novidades += n
    indeterminados += i

    ciclo_cpc = (prov.get("cpc") or {}).get("ciclo")
    n, i = _serie_anual_multi("CPC", URLS_CPC, ciclo_cpc, ano_limite)
    novidades += n
    indeterminados += i

    competencia = (prov.get("cnes") or {}).get("competencia")
    n, i = _competencia_cnes(competencia)
    novidades += n
    indeterminados += i

    print()
    for nome, motivo in FONTES_SEM_SONDAGEM.items():
        print(f"[CHECK] SEM SONDAGEM: {nome} — {motivo}")

    print()
    if novidades:
        print(f"[CHECK] {len(novidades)} fonte(s) com edição nova: "
              f"{', '.join(novidades)}")
    else:
        print("[CHECK] nenhuma edição nova encontrada.")
    if indeterminados:
        print(f"[CHECK] {len(indeterminados)} verificação(ões) INDETERMINADA(s): "
              f"{', '.join(indeterminados)}")
        print("[CHECK] indeterminado NÃO é ausente. Reveja manualmente antes de "
              "concluir que nada mudou.")

    _github_output("fontes_novas", "true" if novidades else "false")
    _github_output("fontes_novas_detalhe", "; ".join(novidades))
    _github_output("fontes_indeterminadas", "true" if indeterminados else "false")
    _github_output("fontes_indeterminadas_detalhe", "; ".join(indeterminados))
    return novidades, indeterminados


# --------------------------------------------------------------------------- #
# Guarda de riqueza
# --------------------------------------------------------------------------- #

def _versao_anterior(caminho_relativo):
    """Conteúdo do arquivo em HEAD, ou None se não houver (repo novo, arquivo novo)."""
    try:
        saida = subprocess.run(
            ["git", "show", f"HEAD:{caminho_relativo}"],
            cwd=str(REPO), capture_output=True, text=True, encoding="utf-8")
        if saida.returncode != 0:
            return None
        return json.loads(saida.stdout)
    except Exception:                                          # noqa: BLE001
        return None


def conferir_riqueza(tolerancia=0):
    """
    Compara a riqueza do conjunto novo com a do publicado em HEAD.

    Aborta se alguma UF perder campos. Não é um teste de valor — é um teste de
    PRESENÇA, que é justamente o que os testes de integridade não fazem: eles
    conferem os campos que conhecem, e um campo que sumiu não é conferido por
    ninguém.
    """
    atual_caminho = DATA / "nacional.json"
    if not atual_caminho.exists():
        raise SystemExit("[RIQUEZA] data/nacional.json não existe — nada a conferir.")

    atual = json.loads(atual_caminho.read_text(encoding="utf-8"))
    anterior = _versao_anterior("data/nacional.json")

    campos_atuais = {u: set(d) for u, d in atual["ufs"].items()}
    n_atual = len(next(iter(campos_atuais.values())))

    if anterior is None:
        print(f"[RIQUEZA] sem versão anterior em HEAD; registrando "
              f"{n_atual} campos por UF como linha de base.")
        return True

    campos_antes = {u: set(d) for u, d in anterior["ufs"].items()}
    problemas = []

    ufs_perdidas = sorted(set(campos_antes) - set(campos_atuais))
    if ufs_perdidas:
        problemas.append(f"UFs que sumiram do conjunto: {ufs_perdidas}")

    for uf, antes in campos_antes.items():
        agora = campos_atuais.get(uf)
        if agora is None:
            continue
        perdidos = sorted(antes - agora)
        if len(perdidos) > tolerancia:
            problemas.append(f"{uf}: perdeu {len(perdidos)} campo(s): {perdidos}")

    n_antes = len(next(iter(campos_antes.values())))
    print(f"[RIQUEZA] campos por UF: {n_antes} em HEAD -> {n_atual} agora")

    if problemas:
        print("[RIQUEZA] FALHOU:", file=sys.stderr)
        for p in problemas:
            print("  -", p, file=sys.stderr)
        raise SystemExit(
            "[RIQUEZA] o conjunto novo é mais pobre que o publicado. "
            "Isso quase sempre significa que um passo do pipeline não rodou. "
            "Nada foi publicado.")

    ganhos = n_atual - n_antes
    if ganhos > 0:
        print(f"[RIQUEZA] OK — {ganhos} campo(s) a mais que a versão publicada.")
    else:
        print("[RIQUEZA] OK — nenhum campo perdido.")
    return True


# --------------------------------------------------------------------------- #

def executar(ano, pular_cnes=False, competencia=None):
    _rodar("extrair_censo.py", "--ano", ano)
    _rodar("ingestao.py", "--ano", ano)
    _rodar("extrair_cpc.py", "--ano-censo", ano)
    if not pular_cnes:
        args = ["--competencia", competencia] if competencia else []
        _rodar("extrair_cnes.py", *args)
    else:
        print("\n[PIPELINE] CNES pulado por pedido; a cobertura de saúde ficará nula "
              "e a proveniência dirá isso.")
    _rodar("extrair_suas.py")
    _rodar("consolidar.py")
    _rodar("registro_autoral.py")

    print("\n[PIPELINE] portão de qualidade")
    _rodar("indices.py", "--autoteste")

    print("\n[PIPELINE] conferência de riqueza")
    conferir_riqueza()

    print("\n[PIPELINE] testes")
    for teste in ("test_catalogo.py", "test_validacao.py", "test_check_fontes.py"):
        caminho = REPO / "tests" / teste
        if not caminho.exists():
            continue
        resultado = subprocess.run([sys.executable, str(caminho)], cwd=str(REPO))
        if resultado.returncode != 0:
            raise SystemExit(f"[PIPELINE] {teste} falhou. Nada foi publicado.")

    print("\n[PIPELINE] tudo passou. Rode `python site/build.py` para gerar o site.")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--check-only", action="store_true",
                   help="só verifica se as fontes têm edição nova")
    p.add_argument("--ano", type=int, default=2024, help="ano do Censo")
    p.add_argument("--competencia", help="competência do CNES (AAAAMM)")
    p.add_argument("--pular-cnes", action="store_true",
                   help="não reextrai o CNES (demorado); a cobertura fica nula")
    p.add_argument("--so-riqueza", action="store_true",
                   help="roda apenas a conferência de riqueza")
    args = p.parse_args()

    if args.check_only:
        verificar_fontes()
        return
    if args.so_riqueza:
        conferir_riqueza()
        return
    executar(args.ano, args.pular_cnes, args.competencia)


if __name__ == "__main__":
    main()
