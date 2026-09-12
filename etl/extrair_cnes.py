"""
etl/extrair_cnes.py
Extrai do CNES as duas metades da cobertura assistencial em Psicologia no SUS,
lendo a base mensal do DATASUS por FTP sem baixar os 700 MB do ZIP.

Uso:
    python etl/extrair_cnes.py                      # competência mais recente
    python etl/extrair_cnes.py --competencia 202607
    python etl/extrair_cnes.py --listar             # competências disponíveis
    python etl/extrair_cnes.py --rebaixar           # ignora o cache e rebaixa

Saída: data/cobertura_cnes.json — por município.

AS DUAS METADES
---------------
  · força de trabalho — municípios com ao menos um vínculo de psicólogo
    (família CBO 2515) em `tbCargaHorariaSus`;
  · rede psicossocial — municípios com estabelecimento que declara o serviço
    especializado 115, ATENÇÃO PSICOSSOCIAL, em `rlEstabServClass`.

Publicadas separadamente porque fundi-las exigiria arbitrar um peso entre "tem
profissional" e "tem serviço", e peso arbitrário é estimativa disfarçada.

O CBO É POR PREFIXO EXATO DE FAMÍLIA, NÃO POR NOME
---------------------------------------------------
A família 2515 reúne as ocupações de psicólogo (251505 a 251555 — clínico,
educacional, hospitalar, jurídico, social, do trabalho, neuropsicólogo e as
demais), todas marcadas TP_CBO_SAUDE = 'S'.

Aqui o prefixo importa mais do que importava em Fonoaudiologia. Lá havia um só
engodo textual; aqui há três, e casar por texto capturaria os três:

    232160  PROFESSOR DE PSICOLOGIA NO ENSINO MÉDIO
    234760  PROFESSOR DE PSICOLOGIA DO ENSINO SUPERIOR
    203525  PESQUISADOR EM PSICOLOGIA

Docência e pesquisa não são assistência. O prefixo 2515 exclui os três; a busca
por "psicólogo" ou "psicologia", não. É o mesmo erro que casar rótulo CINE por
substring cometeria com `Psicopedagogia`, que tem 6.083 registros no Censo.

O SERVIÇO 115 SAI EM TRÊS SUBGRUPOS, NÃO NUM NÚMERO SÓ
-------------------------------------------------------
As onze classificações do serviço 115 cobrem a Rede de Atenção Psicossocial
inteira, e vão de promoção da saúde mental e protagonismo até internação em
regime fechado para dependência química. Somá-las num indicador único mediria
como equivalentes coisas que a política pública trata como opostas, e o número
resultante não responderia pergunta nenhuma. Ficam três subgrupos, mais o
total:

  comunitária   115/002, 115/010, 115/011   atendimento psicossocial aberto,
                                            desinstitucionalização, promoção
  residencial   115/001, 115/004, 115/005,  moradia assistida: residências
                115/006, 115/007            terapêuticas e acolhimento
  internação    115/003, 115/008, 115/009   leito e regime fechado

Cada subgrupo conta ESTABELECIMENTOS DISTINTOS dentro dele, e o total também.
Como um mesmo estabelecimento pode declarar mais de uma classificação, o total
NÃO é a soma dos três — usar a soma no lugar do total contaria o mesmo CAPS
duas vezes.

DUAS FASES, COM CACHE ENTRE ELAS
---------------------------------
Baixar e filtrar leva perto de uma hora: o FTP do DATASUS derruba a maior parte
das conexões que usam REST. Agregar leva segundos. Misturar as duas coisas num
passo só significa pagar a hora de novo a cada ajuste de fórmula, o que na
prática desestimula ajustar a fórmula. As fatias filtradas ficam em
`etl/dados/cnes_<competência>/`, fora do versionamento.

O DOMÍNIO É LIDO POR ÚLTIMO, E PODE FALHAR
-------------------------------------------
`tbClassificacaoServico`, `tbServicoEspecializado` e `tbAtividadeProfissional`
dão o NOME por extenso de cada código. São um luxo: o indicador é o código, e o
código sai das tabelas-fato. Por isso elas vêm depois das três fatias que
importam e com orçamento curto de tentativas — no FTP do DATASUS, insistir doze
vezes com timeout de 300 s numa tabela de 3 KB pode custar uma hora, e custar
uma hora por um rótulo é o tipo de decisão que ninguém tomaria de propósito.
Falhando, os códigos ficam sem nome e a falha é registrada na proveniência.

AS TABELAS AUXILIARES NÃO SÃO O CADASTRO DA REDE
-------------------------------------------------
Existem `rlEstabAtenPsico` e `rlMunAtenPsico` nesta base, e é tentador tomá-las
como o cadastro dos CAPS. Não são: a primeira tem cerca de 1.400 registros —
bem menos que o número conhecido de CAPS no país — e suas colunas
(TP_ESTRUTURA, NU_VAGAS_ACOL_NOTUR, CO_PROFISSIONAL_SUS, CO_CBO,
CO_CNES_REFERENCIA) descrevem atributos de acolhimento, não a existência do
serviço. Servem como detalhe; como denominador, não. A existência do serviço
sai de `rlEstabServClass`, que é tabela-fato de serviço declarado.
"""
import argparse
import csv
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

from rede import ZipRemotoFTP

REPO = Path(__file__).parent.parent
DADOS = REPO / "etl" / "dados"
DATA = REPO / "data"

HOST = "ftp.datasus.gov.br"
DIRETORIO = "/cnes"
PADRAO = "BASE_DE_DADOS_CNES_{competencia}.ZIP"

# Blocos grandes reduzem o número de conexões FTP, e cada conexão é uma aposta:
# o DATASUS derruba boa parte das conexões que usam REST. Blocos pequenos
# multiplicam as apostas; blocos grandes desperdiçam mais a cada queda.
BLOCO = 16 << 20

CBO_PREFIXO = "2515"           # família Psicólogo (251505 .. 251555)

SERVICO_PSICOSSOCIAL = "115"   # ATENÇÃO PSICOSSOCIAL

# Os três subgrupos. A lista é fechada de propósito: uma classificação nova
# numa competência futura NÃO cai em nenhum grupo por acidente — ela aparece em
# `classificacoes_nao_agrupadas` no diagnóstico, para alguém decidir onde
# encaixá-la. Encaixar automaticamente seria decidir por omissão uma questão
# que é de mérito.
SUBGRUPOS = {
    "comunitaria": ["002", "010", "011"],
    "residencial": ["001", "004", "005", "006", "007"],
    "internacao": ["003", "008", "009"],
}
# O 115/008 chama-se UNIDADE DE ATENCAO EM REGIME RESIDENCIAL, e o nome puxa
# para o grupo "residencial". Ele está em "internacao" de propósito: é o código
# das comunidades terapêuticas, regime fechado para dependência química. O
# grupo residencial reúne o oposto disso — residência terapêutica e unidade de
# acolhimento são moradia na cidade, e existem justamente para desfazer a
# internação. Agrupar pelo nome, e não pelo que a política pública faz, juntaria
# o manicômio com o que veio para substituí-lo.
ROTULOS_SUBGRUPO = {
    "comunitaria": "Atenção psicossocial comunitária (aberta)",
    "residencial": "Moradia assistida e acolhimento",
    "internacao": "Leito e regime fechado",
}
GRUPO_POR_CLASSIFICACAO = {c: g for g, cs in SUBGRUPOS.items() for c in cs}

UF_POR_CODIGO = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP",
    "17": "TO", "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB",
    "26": "PE", "27": "AL", "28": "SE", "29": "BA", "31": "MG", "32": "ES",
    "33": "RJ", "35": "SP", "41": "PR", "42": "SC", "43": "RS", "50": "MS",
    "51": "MT", "52": "GO", "53": "DF",
}

# Fração de registros cujo CO_UNIDADE não existe em NENHUM estabelecimento do
# cadastro. Diferente de "estabelecimento desabilitado", que é exclusão
# deliberada e pode ser alta sem indicar defeito nenhum.
LIMITE_SEM_CADASTRO = 0.02

csv.field_size_limit(1 << 24)


def _limpo(valor):
    return (valor or "").strip().strip('"')


def competencias_disponiveis():
    z = ZipRemotoFTP(HOST, DIRETORIO, PADRAO.format(competencia="000000"))
    nomes = z.listar_diretorio()
    return sorted(
        m.group(1) for m in
        (re.match(r"BASE_DE_DADOS_CNES_(\d{6})\.ZIP$", n, re.I) for n in nomes)
        if m
    )


def _membro(z, sufixo, competencia, obrigatorio=True):
    alvo = z.localizar(sufixo.lower(), competencia)
    if not alvo and obrigatorio:
        raise SystemExit(f"[ERRO] membro {sufixo}{competencia} não encontrado no ZIP")
    return alvo


# --------------------------------------------------------------------------- #
# FASE 1 — baixar e filtrar (cara, cacheada)
# --------------------------------------------------------------------------- #

def _escrever(caminho, cabecalho, linhas):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        escritor = csv.writer(f, delimiter=";")
        escritor.writerow(cabecalho)
        escritor.writerows(linhas)


def _ler_dominio(z, competencia):
    """
    Nomes oficiais das classificações do 115 e das ocupações da família 2515.

    Lidos da própria base, não digitados aqui. Um rótulo digitado à mão numa
    constante envelhece em silêncio: o código continua certo, o nome na tela
    passa a ser o de outra coisa, e nada acusa. As tabelas de domínio somam
    menos de 200 KB, então isso custa segundos.

    Opcional de propósito: se um layout mudar de nome, os códigos continuam
    corretos e o rótulo fica ausente — declarado ausente, não inventado.
    """
    dominio = {"classificacoes": {}, "ocupacoes": {}, "servico": None,
               "falhas": []}

    # Orçamento curto e próprio. O padrão de 12 tentativas com timeout de 300 s
    # existe para as tabelas-fato, onde vale a pena insistir; aqui uma insistência
    # dessas custaria uma hora para obter um rótulo que o site sabe viver sem.
    z_curto = ZipRemotoFTP(z.host, z.diretorio, z.nome, timeout=60, tentativas=3)
    z_curto._indice = z.indice()          # o índice já foi lido; não relê
    z_curto._tamanho = z.tamanho()

    def _tentar(sufixo, consumir, rotulo):
        alvo = _membro(z_curto, sufixo, competencia, obrigatorio=False)
        if not alvo:
            dominio["falhas"].append(f"{sufixo}: membro não localizado no ZIP")
            print(f"[CNES] {rotulo}: membro não localizado; os códigos ficam "
                  "sem rótulo oficial (e sem rótulo inventado).")
            return
        try:
            with z_curto.membro_arquivo(alvo) as f:
                consumir(csv.DictReader(f, delimiter=";"))
        except Exception as e:                                 # noqa: BLE001
            dominio["falhas"].append(f"{sufixo}: {type(e).__name__}")
            print(f"[CNES] {rotulo}: leitura falhou ({type(e).__name__}). "
                  "Os códigos continuam corretos e ficam sem rótulo por "
                  "extenso — o que falta é o nome, não a medida.")

    def _classificacoes(leitor):
        for linha in leitor:
            if _limpo(linha.get("CO_SERVICO_ESPECIALIZADO")) != SERVICO_PSICOSSOCIAL:
                continue
            dominio["classificacoes"][
                _limpo(linha.get("CO_CLASSIFICACAO_SERVICO"))] = _limpo(
                    linha.get("DS_CLASSIFICACAO_SERVICO"))

    def _servico(leitor):
        for linha in leitor:
            if _limpo(linha.get("CO_SERVICO_ESPECIALIZADO")) == SERVICO_PSICOSSOCIAL:
                dominio["servico"] = _limpo(linha.get("DS_SERVICO_ESPECIALIZADO"))

    def _ocupacoes(leitor):
        for linha in leitor:
            cbo = _limpo(linha.get("CO_CBO"))
            if cbo.startswith(CBO_PREFIXO):
                dominio["ocupacoes"][cbo] = _limpo(
                    linha.get("DS_ATIVIDADE_PROFISSIONAL"))

    _tentar("tbClassificacaoServico", _classificacoes, "classificações do 115")
    print(f"[CNES] {len(dominio['classificacoes'])} classificações do serviço "
          f"{SERVICO_PSICOSSOCIAL} lidas da tabela de domínio")

    _tentar("tbServicoEspecializado", _servico, "nome do serviço 115")
    _tentar("tbAtividadeProfissional", _ocupacoes, f"ocupações da família {CBO_PREFIXO}")
    print(f"[CNES] {len(dominio['ocupacoes'])} ocupações da família "
          f"{CBO_PREFIXO} lidas da tabela de domínio")

    return dominio


def baixar_fatias(competencia, cache, rebaixar=False):
    """Grava as fatias filtradas em `cache`. Só baixa o que faltar."""
    alvos = {
        "estabelecimentos": cache / "estabelecimentos.csv",
        "vinculos": cache / "vinculos_psicologia.csv",
        "servicos": cache / "servicos_psicossocial.csv",
        "dominio": cache / "dominio.json",
    }
    if not rebaixar and all(p.exists() for p in alvos.values()):
        print(f"[CNES] usando fatias já filtradas em {cache}")
        return alvos

    nome = PADRAO.format(competencia=competencia)
    z = ZipRemotoFTP(HOST, DIRETORIO, nome)
    print(f"[CNES] {nome} — {z.tamanho() / 1048576:.0f} MB no servidor; "
          "lendo só os membros necessários")

    if rebaixar or not alvos["estabelecimentos"].exists():
        alvo = _membro(z, "tbEstabelecimento", competencia)
        print(f"[CNES] lendo {alvo} ... (285 MB descomprimidos)")
        linhas, ativos, desabilitados = [], 0, 0
        with z.membro_arquivo(alvo, bloco=BLOCO) as f:
            for linha in csv.DictReader(f, delimiter=";"):
                unidade = _limpo(linha.get("CO_UNIDADE"))
                if not unidade:
                    continue
                # Guardamos TODOS, com uma coluna dizendo se está ativo. O
                # desabilitado precisa continuar conhecido: é ele que permite
                # distinguir "excluído de propósito" de "não encontrado", e essa
                # distinção é o que dá sentido à guarda de junção.
                ativo = "0" if _limpo(linha.get("CO_MOTIVO_DESAB")) else "1"
                if ativo == "1":
                    ativos += 1
                else:
                    desabilitados += 1
                linhas.append([unidade,
                               _limpo(linha.get("CO_MUNICIPIO_GESTOR")),
                               _limpo(linha.get("CO_ESTADO_GESTOR")),
                               ativo])
        _escrever(alvos["estabelecimentos"],
                  ["CO_UNIDADE", "CO_MUNICIPIO_GESTOR", "CO_ESTADO_GESTOR", "ATIVO"],
                  linhas)
        print(f"[CNES] {ativos} estabelecimentos ativos, "
              f"{desabilitados} desabilitados -> {alvos['estabelecimentos'].name}")

    if rebaixar or not alvos["vinculos"].exists():
        alvo = _membro(z, "tbCargaHorariaSus", competencia)
        print(f"[CNES] lendo {alvo} ... (834 MB descomprimidos; leitura em fluxo)")
        linhas, total = [], 0
        with z.membro_arquivo(alvo, bloco=BLOCO) as f:
            for linha in csv.DictReader(f, delimiter=";"):
                total += 1
                cbo = _limpo(linha.get("CO_CBO"))
                if not cbo.startswith(CBO_PREFIXO):
                    continue
                linhas.append([_limpo(linha.get("CO_UNIDADE")),
                               _limpo(linha.get("CO_PROFISSIONAL_SUS")),
                               cbo,
                               _limpo(linha.get("TP_SUS_NAO_SUS"))])
        _escrever(alvos["vinculos"],
                  ["CO_UNIDADE", "CO_PROFISSIONAL_SUS", "CO_CBO", "TP_SUS_NAO_SUS"],
                  linhas)
        print(f"[CNES] {total} vínculos lidos; {len(linhas)} de CBO "
              f"{CBO_PREFIXO}xx -> {alvos['vinculos'].name}")

    if rebaixar or not alvos["servicos"].exists():
        alvo = _membro(z, "rlEstabServClass", competencia)
        print(f"[CNES] lendo {alvo} ...")
        linhas, total = [], 0
        with z.membro_arquivo(alvo, bloco=BLOCO) as f:
            for linha in csv.DictReader(f, delimiter=";"):
                total += 1
                if _limpo(linha.get("CO_SERVICO")) != SERVICO_PSICOSSOCIAL:
                    continue
                linhas.append([_limpo(linha.get("CO_UNIDADE")),
                               _limpo(linha.get("CO_SERVICO")),
                               _limpo(linha.get("CO_CLASSIFICACAO")),
                               _limpo(linha.get("ST_ATIVO_SN")),
                               _limpo(linha.get("CO_AMBULATORIAL_SUS")),
                               _limpo(linha.get("CO_HOSPITALAR_SUS"))])
        _escrever(alvos["servicos"],
                  ["CO_UNIDADE", "CO_SERVICO", "CO_CLASSIFICACAO", "ST_ATIVO_SN",
                   "CO_AMBULATORIAL_SUS", "CO_HOSPITALAR_SUS"],
                  linhas)
        print(f"[CNES] {total} registros de serviço; {len(linhas)} do serviço "
              f"{SERVICO_PSICOSSOCIAL} -> {alvos['servicos'].name}")

    # Por último, e sem poder atrapalhar: as tabelas de domínio só acrescentam
    # o rótulo por extenso de cada código. O dado já está lido a esta altura.
    if rebaixar or not alvos["dominio"].exists():
        alvos["dominio"].parent.mkdir(parents=True, exist_ok=True)
        alvos["dominio"].write_text(
            json.dumps(_ler_dominio(z, competencia), ensure_ascii=False, indent=1),
            encoding="utf-8")

    return alvos


# --------------------------------------------------------------------------- #
# FASE 2 — agregar (barata, refaz à vontade)
# --------------------------------------------------------------------------- #

def carregar_estabelecimentos(caminho):
    """Devolve (ativos, conhecidos): dict CO_UNIDADE->(mun, uf) e set de todos."""
    ativos, conhecidos = {}, set()
    with open(caminho, encoding="utf-8") as f:
        for linha in csv.DictReader(f, delimiter=";"):
            unidade = linha["CO_UNIDADE"]
            conhecidos.add(unidade)
            if linha["ATIVO"] == "1" and linha["CO_MUNICIPIO_GESTOR"]:
                ativos[unidade] = (linha["CO_MUNICIPIO_GESTOR"],
                                   UF_POR_CODIGO.get(linha["CO_ESTADO_GESTOR"]))
    return ativos, conhecidos


def _classificar(unidade, ativos, conhecidos, contadores):
    """
    Resolve o município de um CO_UNIDADE e classifica o que não resolve.

    Três desfechos, e a diferença entre eles é o ponto:
      · resolveu                   -> devolve o município
      · existe, mas desabilitado   -> exclusão DELIBERADA, esperada, não é erro
      · não existe no cadastro     -> falha de junção; é isso que a guarda vigia
    """
    local = ativos.get(unidade)
    if local:
        return local[0]
    if unidade in conhecidos:
        contadores["desabilitado"] += 1
    else:
        contadores["sem_cadastro"] += 1
    return None


def forca_de_trabalho(caminho, ativos, conhecidos):
    """
    Conta PROFISSIONAIS DISTINTOS por município, não vínculos: o mesmo
    psicólogo pode ter três vínculos no mesmo município, e contá-lo três vezes
    transformaria precariedade de vínculo em abundância de força de trabalho.
    """
    sus, todos = defaultdict(set), defaultdict(set)
    contadores = defaultdict(int)
    por_cbo = defaultdict(int)
    total = 0
    with open(caminho, encoding="utf-8") as f:
        for i, linha in enumerate(csv.DictReader(f, delimiter=";")):
            total += 1
            por_cbo[linha["CO_CBO"]] += 1
            municipio = _classificar(linha["CO_UNIDADE"], ativos, conhecidos,
                                     contadores)
            if not municipio:
                continue
            chave = linha["CO_PROFISSIONAL_SUS"] or f"{linha['CO_UNIDADE']}:{i}"
            todos[municipio].add(chave)
            if linha["TP_SUS_NAO_SUS"].upper() == "S":
                sus[municipio].add(chave)
    return sus, todos, {
        "vinculos_psicologia": total,
        "vinculos_por_cbo": dict(sorted(por_cbo.items())),
        "vinculos_em_estabelecimento_desabilitado": contadores["desabilitado"],
        "vinculos_sem_cadastro": contadores["sem_cadastro"],
    }


def rede_psicossocial(caminho, ativos, conhecidos):
    """
    Estabelecimentos com serviço 115 por município, no total e por subgrupo.

    Cada subgrupo conta estabelecimentos DISTINTOS dentro dele. O total também
    conta distintos, e por isso NÃO é a soma dos três: um mesmo CAPS pode
    declarar atendimento psicossocial e acolhimento, e somar os subgrupos o
    contaria duas vezes.
    """
    total_por_municipio = defaultdict(set)
    declarado_por_municipio = defaultdict(set)
    por_grupo = {g: defaultdict(set) for g in SUBGRUPOS}
    detalhe = defaultdict(lambda: defaultdict(set))
    contadores = defaultdict(int)
    nao_agrupadas = defaultdict(int)
    total = com_situacao = 0

    with open(caminho, encoding="utf-8") as f:
        for linha in csv.DictReader(f, delimiter=";"):
            total += 1
            if linha.get("ST_ATIVO_SN"):
                com_situacao += 1
            municipio = _classificar(linha["CO_UNIDADE"], ativos, conhecidos,
                                     contadores)
            if not municipio:
                continue
            classificacao = linha["CO_CLASSIFICACAO"]
            unidade = linha["CO_UNIDADE"]
            declarado_por_municipio[municipio].add(unidade)
            detalhe[municipio][f"{linha['CO_SERVICO']}/{classificacao}"].add(unidade)
            # Só o que é ofertado AO SUS entra nos indicadores: a rede de
            # atenção psicossocial é política pública, e clínica privada que
            # declara o serviço 115 no cadastro não faz parte dela.
            if not (linha.get("CO_AMBULATORIAL_SUS") == "1"
                    or linha.get("CO_HOSPITALAR_SUS") == "1"):
                continue
            total_por_municipio[municipio].add(unidade)
            grupo = GRUPO_POR_CLASSIFICACAO.get(classificacao)
            if grupo:
                por_grupo[grupo][municipio].add(unidade)
            else:
                nao_agrupadas[classificacao] += 1

    if nao_agrupadas:
        print(f"[CNES] ATENÇÃO: classificações do serviço "
              f"{SERVICO_PSICOSSOCIAL} sem subgrupo declarado: "
              f"{dict(nao_agrupadas)}. Entram no total e em nenhum subgrupo — "
              "decida onde encaixá-las em SUBGRUPOS.")

    return total_por_municipio, declarado_por_municipio, por_grupo, detalhe, {
        "servicos_psicossociais": total,
        "servicos_com_situacao_preenchida": com_situacao,
        "st_ativo_sn_vazio_no_export": com_situacao == 0,
        "servicos_em_estabelecimento_desabilitado": contadores["desabilitado"],
        "servicos_sem_cadastro": contadores["sem_cadastro"],
        "classificacoes_nao_agrupadas": dict(nao_agrupadas),
    }


def conferir_juncao(casos, limite=LIMITE_SEM_CADASTRO):
    """
    Aborta se registros demais apontarem para CO_UNIDADE que não existe.

    Vigia SÓ o desconhecido. Somar o desabilitado junto reprovaria execuções
    corretas: estabelecimento fechado é exclusão que o indicador faz de
    propósito, e sua fração pode ser alta sem indicar defeito nenhum. Uma
    guarda que dispara no comportamento certo é pior que nenhuma, porque ensina
    a ignorá-la.

    A junção é por CO_UNIDADE, e o formato do campo não é uniforme na base. Se
    o layout mudar numa competência futura, a junção degrada em silêncio: o
    pipeline roda, os testes passam, e a cobertura despenca como se a rede
    tivesse encolhido. Um número que cai por defeito de junção é pior que um
    erro, porque parece notícia.
    """
    problemas = []
    for rotulo, total, desconhecidos, desabilitados in casos:
        if total <= 0:
            problemas.append(f"{rotulo}: nenhum registro lido")
            continue
        fracao = desconhecidos / total
        marca = "OK" if fracao <= limite else "FALHOU"
        print(f"[JUNCAO] {marca}  {rotulo}: {desconhecidos}/{total} "
              f"({fracao:.2%}) sem cadastro; "
              f"{desabilitados} ({desabilitados / total:.1%}) em "
              "estabelecimento desabilitado (exclusão esperada)")
        if fracao > limite:
            problemas.append(
                f"{rotulo}: {fracao:.2%} sem cadastro (limite {limite:.0%})")
    if problemas:
        raise SystemExit("[ERRO] junção CO_UNIDADE degradada:\n  - "
                         + "\n  - ".join(problemas))


def montar(competencia, sus, todos, rede, rede_declarada, por_grupo, detalhe,
           dominio, diagnostico):
    municipios = {}
    chaves = set(sus) | set(todos) | set(rede_declarada)
    for grupo in por_grupo.values():
        chaves |= set(grupo)
    for codigo in chaves:
        registro = {
            "psicologos_sus": len(sus.get(codigo, ())) or None,
            "psicologos_total": len(todos.get(codigo, ())) or None,
            # O indicador conta o que atende pelo SUS; o total declarado
            # (público mais privado) sai ao lado, e a distância entre os dois
            # diz quanto da rede psicossocial do município é pública.
            "estabelecimentos_raps": len(rede.get(codigo, ())) or None,
            "estabelecimentos_raps_total": len(
                rede_declarada.get(codigo, ())) or None,
            "servicos": sorted(detalhe.get(codigo, {})) or None,
        }
        for grupo in SUBGRUPOS:
            registro[f"raps_{grupo}"] = len(por_grupo[grupo].get(codigo, ())) or None
        municipios[codigo] = registro

    arquivo = PADRAO.format(competencia=competencia)
    classificacoes = (dominio or {}).get("classificacoes") or {}
    subgrupos_declarados = {
        grupo: {
            "rotulo": ROTULOS_SUBGRUPO[grupo],
            "classificacoes": {
                f"{SERVICO_PSICOSSOCIAL}/{c}": classificacoes.get(c)
                for c in codigos
            },
        }
        for grupo, codigos in SUBGRUPOS.items()
    }

    return {
        "metadados": {
            "fonte": "Cadastro Nacional de Estabelecimentos de Saúde (CNES/DATASUS)",
            "arquivo": arquivo,
            "url": f"ftp://{HOST}{DIRETORIO}/{arquivo}",
            "competencia": competencia,          # do ARQUIVO, não do calendário
            "cbo_familia": CBO_PREFIXO,
            "cbo_ocupacoes": (dominio or {}).get("ocupacoes") or {},
            "cbo_criterio": (
                "prefixo exato da família 2515. Casar por texto capturaria "
                "232160 (professor de Psicologia no ensino médio), 234760 "
                "(professor do ensino superior) e 203525 (pesquisador em "
                "Psicologia) — docência e pesquisa, não assistência."
            ),
            "servico": SERVICO_PSICOSSOCIAL,
            "servico_nome": (dominio or {}).get("servico"),
            "dominio_nao_lido": (dominio or {}).get("falhas") or None,
            "subgrupos": subgrupos_declarados,
            "servico_criterio_sus": (
                "Os indicadores contam estabelecimentos que ofertam o serviço "
                "AO SUS (CO_AMBULATORIAL_SUS ou CO_HOSPITALAR_SUS = 1). O "
                "total declarado, que inclui o privado, sai em "
                "`estabelecimentos_raps_total`: serviço declarado no cadastro "
                "não é serviço público, e a RAPS é política pública."
            ),
            "st_ativo_sn_nao_filtra": (
                "A coluna ST_ATIVO_SN de rlEstabServClass vem vazia em todas as "
                "linhas deste export, então não há como excluir serviço "
                "marcado como inativo. O filtro que existia aqui lia coluna "
                "sempre em branco e nunca excluiu nada; agora a ausência é "
                "contada e declarada."
            ),
            "subgrupos_nao_somam_o_total": (
                "O total conta estabelecimentos distintos com qualquer "
                "classificação do serviço 115. Como um mesmo estabelecimento "
                "pode declarar mais de uma, a soma dos três subgrupos é maior "
                "que o total — e não deve ser usada no lugar dele."
            ),
            "tabelas_auxiliares_nao_usadas": (
                "rlEstabAtenPsico e rlMunAtenPsico existem nesta base e NÃO "
                "foram usadas como cadastro da rede: a primeira tem cerca de "
                "1.400 registros, bem menos que o número conhecido de CAPS, e "
                "suas colunas descrevem atributos de acolhimento (estrutura, "
                "vagas de acolhimento noturno, profissional de referência), "
                "não a existência do serviço. A existência sai de "
                "rlEstabServClass, que é tabela-fato de serviço declarado."
            ),
            "extraido_em": date.today().isoformat(),
            "diagnostico": diagnostico,
        },
        "municipios": municipios,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--competencia", help="AAAAMM; default: a mais recente publicada")
    p.add_argument("--listar", action="store_true",
                   help="lista as competências disponíveis e sai")
    p.add_argument("--rebaixar", action="store_true",
                   help="ignora o cache de fatias e baixa tudo de novo")
    p.add_argument("--saida", default=str(DATA / "cobertura_cnes.json"))
    args = p.parse_args()

    if args.listar:
        comps = competencias_disponiveis()
        print(f"{len(comps)} competências: {comps[0]} .. {comps[-1]}")
        print("últimas 12:", ", ".join(comps[-12:]))
        return

    competencia = args.competencia
    if not competencia:
        comps = competencias_disponiveis()
        if not comps:
            raise SystemExit("[ERRO] nenhuma competência encontrada no FTP")
        competencia = comps[-1]
        print(f"[CNES] competência mais recente: {competencia}")

    cache = DADOS / f"cnes_{competencia}"
    fatias = baixar_fatias(competencia, cache, args.rebaixar)

    ativos, conhecidos = carregar_estabelecimentos(fatias["estabelecimentos"])
    print(f"[CNES] {len(ativos)} estabelecimentos ativos de "
          f"{len(conhecidos)} cadastrados")

    dominio = json.loads(fatias["dominio"].read_text(encoding="utf-8"))
    sus, todos, diag_ch = forca_de_trabalho(fatias["vinculos"], ativos, conhecidos)
    rede, rede_declarada, por_grupo, detalhe, diag_sc = rede_psicossocial(
        fatias["servicos"], ativos, conhecidos)

    conferir_juncao([
        ("vínculos de psicólogo",
         diag_ch["vinculos_psicologia"],
         diag_ch["vinculos_sem_cadastro"],
         diag_ch["vinculos_em_estabelecimento_desabilitado"]),
        ("serviços de atenção psicossocial",
         diag_sc["servicos_psicossociais"],
         diag_sc["servicos_sem_cadastro"],
         diag_sc["servicos_em_estabelecimento_desabilitado"]),
    ])

    saida = montar(competencia, sus, todos, rede, rede_declarada, por_grupo,
                   detalhe, dominio, {**diag_ch, **diag_sc})
    Path(args.saida).parent.mkdir(parents=True, exist_ok=True)
    Path(args.saida).write_text(
        json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")

    n_forca = sum(1 for m in saida["municipios"].values() if m["psicologos_sus"])
    n_rede = sum(1 for m in saida["municipios"].values()
                 if m["estabelecimentos_raps"])
    n_rede_total = sum(1 for m in saida["municipios"].values()
                       if m["estabelecimentos_raps_total"])
    print(f"\n[CNES] municípios com psicólogo no SUS: {n_forca}")
    print(f"[CNES] municípios com serviço de atenção psicossocial ao SUS: "
          f"{n_rede} (declarado por qualquer natureza: {n_rede_total})")
    for grupo in SUBGRUPOS:
        n = sum(1 for m in saida["municipios"].values() if m[f"raps_{grupo}"])
        print(f"[CNES]   {ROTULOS_SUBGRUPO[grupo]}: {n} municípios")
    print(f"[CNES] -> {args.saida}")


if __name__ == "__main__":
    main()
