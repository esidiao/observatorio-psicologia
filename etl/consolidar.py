"""
etl/consolidar.py
Junta as quatro fontes num único conjunto publicável e aplica os índices.

Uso:
    python etl/consolidar.py

Entrada:  data/bruto.json           (Censo, de ingestao.py)
          data/qualidade.json       (CPC, de extrair_cpc.py)
          data/cobertura_cnes.json  (CNES, de extrair_cnes.py)
          data/cobertura_suas.json  (CadSUAS, de extrair_suas.py)
Saída:    data/nacional.json
          data/municipios/<UF>.json
          data/_proveniencia.json

A ORDEM IMPORTA
---------------
`ingestao.py` produz `vagas_presencial` e `vagas_ead`; só depois disso faz
sentido calcular `pct_ead`, `HHI` sobre a capacidade total e o ICT. Rodar o
consolidador antes da ingestão grava `None` em cadeia sem reclamar de nada — o
arquivo fica com as chaves certas e os valores vazios, e nenhum teste de
integridade repara, porque as chaves existem.

FONTE AUSENTE NÃO VIRA ZERO
---------------------------
Se `cobertura_cnes.json` não existir, os campos de cobertura ficam `None` e o
conjunto sai marcado com a fonte faltando na proveniência. O que não acontece é
o ICAP virar 0,0 — isso afirmaria que nenhum município do país tem psicólogo no
SUS, uma afirmação forte sustentada por um arquivo que não foi lido.

MAS ZERO LIDO CONTINUA ZERO
---------------------------
O contrário também vale, e aqui é mais fácil de errar. Quando a fonte FOI lida
e o município não tem o serviço, o valor é 0 — medida, não lacuna. É por isso
que `juntar_cobertura` distingue "não há arquivo" de "há arquivo e o município
não aparece nele": no primeiro caso escreve None, no segundo escreve 0.
"""
import argparse
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

from indices import aplicar, por_100k

REPO = Path(__file__).parent.parent
DATA = REPO / "data"

# O código IBGE começa com o código da UF, então dois dígitos bastam para saber
# a que estado um município pertence. Vale para o CNES e para o CadSUAS, que
# usam os mesmos 6 dígitos sem verificador.
UF_POR_CODIGO = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP",
    "17": "TO", "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB",
    "26": "PE", "27": "AL", "28": "SE", "29": "BA", "31": "MG", "32": "ES",
    "33": "RJ", "35": "SP", "41": "PR", "42": "SC", "43": "RS", "50": "MS",
    "51": "MT", "52": "GO", "53": "DF",
}

SUBGRUPOS_RAPS = ("comunitaria", "residencial", "internacao")

# Campos que cada fonte entrega, nomeados UMA vez. Repetir a lista no ramo do
# "sem fonte" foi o que fez um campo sumir do conjunto em vez de sair nulo, no
# projeto de Farmácia: o campo não existia, e campo ausente não aparece como
# "sem dados" — some da página inteira, sem alarme nenhum.
CAMPOS_CNES_UF = (
    ["municipios_com_psicologo", "municipios_com_raps",
     "psicologos_sus", "psicologos_por_100k", "estabelecimentos_raps"]
    + [f"municipios_com_raps_{g}" for g in SUBGRUPOS_RAPS]
)
CAMPOS_CNES_MUNICIPIO = (
    ["psicologos_sus", "estabelecimentos_raps", "servicos_raps"]
    + [f"raps_{g}" for g in SUBGRUPOS_RAPS]
)
CAMPOS_SUAS_UF = ["municipios_com_cras", "municipios_com_creas",
                  "cras_total", "creas_total",
                  "cras_por_100k", "creas_por_100k"]
CAMPOS_SUAS_MUNICIPIO = ["cras", "creas"]


def _ler(caminho, obrigatorio=True):
    caminho = Path(caminho)
    if caminho.exists():
        return json.loads(caminho.read_text(encoding="utf-8"))
    if obrigatorio:
        raise SystemExit(f"[ERRO] {caminho} ausente — rode o passo anterior do pipeline.")
    print(f"[CONSOLIDAR] {caminho.name} ausente; os campos dessa fonte ficam nulos.")
    return None


def _nulos(destino, campos):
    for campo in campos:
        destino[campo] = None


def juntar_qualidade(ufs, qualidade):
    """Copia os indicadores de qualidade do CPC para cada UF."""
    campos = ("n_cursos_avaliados", "n_com_cpc", "n_com_idd",
              "concluintes_participantes", "CPC", "CPC_cont", "ENADE_cont",
              "IDD", "pct_doc_mestres", "pct_doc_doutores",
              "pct_doc_regime_integral", "dim_didatico_pedagogica",
              "dim_infraestrutura", "dim_oportunidade_formacao",
              "vagas_avaliadas")
    por_uf = (qualidade or {}).get("ufs", {})
    for sigla, d in ufs.items():
        q = por_uf.get(sigla, {})
        for campo in campos:
            d[campo] = q.get(campo)
        d["tem_avaliacao"] = bool(q)
    return ufs


def juntar_cobertura(ufs, municipios_por_uf, cobertura):
    """
    Agrega a cobertura do CNES por UF e anexa aos municípios.

    O CNES identifica município por código IBGE de 6 dígitos (sem o dígito
    verificador); o Censo usa 7. A junção é pelos 6 primeiros — não por nome,
    que tem grafia divergente entre as bases e homônimos entre UFs.
    """
    if not cobertura:
        for d in ufs.values():
            _nulos(d, CAMPOS_CNES_UF)
        for lista in municipios_por_uf.values():
            for m in lista:
                _nulos(m, CAMPOS_CNES_MUNICIPIO)
        return ufs, municipios_por_uf

    por_municipio = cobertura["municipios"]

    com_psicologo = defaultdict(int)
    com_raps = defaultdict(int)
    com_raps_grupo = {g: defaultdict(int) for g in SUBGRUPOS_RAPS}
    profissionais = defaultdict(int)
    estabelecimentos = defaultdict(int)

    for codigo, m in por_municipio.items():
        uf = UF_POR_CODIGO.get(str(codigo)[:2])
        if not uf:
            continue
        if m.get("psicologos_sus"):
            com_psicologo[uf] += 1
            profissionais[uf] += m["psicologos_sus"]
        if m.get("estabelecimentos_raps"):
            com_raps[uf] += 1
            estabelecimentos[uf] += m["estabelecimentos_raps"]
        for grupo in SUBGRUPOS_RAPS:
            if m.get(f"raps_{grupo}"):
                com_raps_grupo[grupo][uf] += 1

    for sigla, d in ufs.items():
        # A fonte FOI lida: um estado que não aparece nos agregados tem zero,
        # não "sem dados". Zero aqui é medida.
        d["municipios_com_psicologo"] = com_psicologo.get(sigla, 0)
        d["municipios_com_raps"] = com_raps.get(sigla, 0)
        for grupo in SUBGRUPOS_RAPS:
            d[f"municipios_com_raps_{grupo}"] = com_raps_grupo[grupo].get(sigla, 0)
        d["psicologos_sus"] = profissionais.get(sigla, 0)
        d["estabelecimentos_raps"] = estabelecimentos.get(sigla, 0)
        d["psicologos_por_100k"] = por_100k(profissionais.get(sigla, 0),
                                            d.get("populacao"))

    for uf, lista in municipios_por_uf.items():
        for m in lista:
            cnes = por_municipio.get(str(m["codigo"])[:6], {})
            m["psicologos_sus"] = cnes.get("psicologos_sus")
            m["estabelecimentos_raps"] = cnes.get("estabelecimentos_raps")
            m["servicos_raps"] = cnes.get("servicos")
            for grupo in SUBGRUPOS_RAPS:
                m[f"raps_{grupo}"] = cnes.get(f"raps_{grupo}")

    return ufs, municipios_por_uf


def juntar_suas(ufs, municipios_por_uf, suas):
    """
    Agrega a rede socioassistencial por UF e anexa aos municípios.

    O CadSUAS devolve linha para os 5.571 municípios, então "não tem CREAS" é
    leitura, não silêncio: o município aparece com 0. É a diferença entre os
    2.813 municípios medidos sem CREAS e um município que ninguém apurou — e
    apagá-la aqui esvaziaria o indicador.
    """
    if not suas:
        for d in ufs.values():
            _nulos(d, CAMPOS_SUAS_UF)
        for lista in municipios_por_uf.values():
            for m in lista:
                _nulos(m, CAMPOS_SUAS_MUNICIPIO)
        return ufs, municipios_por_uf

    por_municipio = suas["municipios"]
    com_cras = defaultdict(int)
    com_creas = defaultdict(int)
    cras = defaultdict(int)
    creas = defaultdict(int)

    for codigo, m in por_municipio.items():
        uf = UF_POR_CODIGO.get(str(codigo)[:2])
        if not uf:
            continue
        if m.get("cras"):
            com_cras[uf] += 1
            cras[uf] += m["cras"]
        if m.get("creas"):
            com_creas[uf] += 1
            creas[uf] += m["creas"]

    for sigla, d in ufs.items():
        d["municipios_com_cras"] = com_cras.get(sigla, 0)
        d["municipios_com_creas"] = com_creas.get(sigla, 0)
        d["cras_total"] = cras.get(sigla, 0)
        d["creas_total"] = creas.get(sigla, 0)
        d["cras_por_100k"] = por_100k(cras.get(sigla, 0), d.get("populacao"))
        d["creas_por_100k"] = por_100k(creas.get(sigla, 0), d.get("populacao"))

    for uf, lista in municipios_por_uf.items():
        for m in lista:
            registro = por_municipio.get(str(m["codigo"])[:6], {})
            m["cras"] = registro.get("cras")
            m["creas"] = registro.get("creas")

    return ufs, municipios_por_uf


def limitacoes(ufs, qualidade, cobertura, suas):
    """
    O que não foi medido, escrito por extenso.

    Montada a partir do conjunto, não digitada: uma limitação digitada à mão
    envelhece calada — o texto continua afirmando o que era verdade na edição
    anterior enquanto o número já mudou.
    """
    itens = []

    sem_ead = sorted(s for s, d in ufs.items() if not d.get("vagas_ead"))
    sem_polo = sorted(s for s, d in ufs.items() if not d.get("ead_polos_registros"))
    itens.append(
        f"A EaD quase não existe em Psicologia: {sum(d.get('vagas_ead') or 0 for d in ufs.values())} "
        f"vagas a distância contra {sum(d.get('vagas_presencial') or 0 for d in ufs.values())} "
        f"presenciais. {len(sem_ead)} das {len(ufs)} UFs não têm nenhuma vaga "
        f"EaD e {len(sem_polo)} não têm nenhum polo ({', '.join(sem_polo)}). "
        "Esses valores são ZERO medido, não ausência de dado, e os indicadores "
        "derivados da EaD são publicados assim — nulos só onde a apuração "
        "realmente faltou.")

    itens.append(
        "HHI por instituição e HHI por mantenedora ficam próximos em quase toda "
        "UF. Nos observatórios em que a EaD é grande, a distância entre os dois "
        "mede o peso dos grandes grupos educacionais; aqui, com 0,2% da "
        "capacidade a distância, não há esse peso a revelar. A proximidade é "
        "achado, não erro de cálculo.")

    if qualidade:
        avaliadas = {s for s, d in ufs.items() if d.get("tem_avaliacao")}
        sem = sorted(set(ufs) - avaliadas)
        if sem:
            itens.append(
                f"UFs com oferta e sem nenhum curso no ciclo do CPC: "
                f"{', '.join(sem)}. Os indicadores de qualidade ficam nulos "
                "nelas, não zerados.")
        else:
            itens.append(
                f"Todas as {len(ufs)} UFs têm curso avaliado no ciclo do CPC "
                f"{qualidade['metadados'].get('ciclo')} — cobertura de "
                "avaliação total, ao contrário do que ocorre em cursos menores.")
    else:
        itens.append("O ciclo do CPC não foi lido; todos os indicadores de "
                     "qualidade estão nulos.")

    if cobertura:
        itens.append(
            "A rede psicossocial (serviço 115 do CNES, ATENÇÃO PSICOSSOCIAL) é "
            "publicada em três subgrupos — comunitário, moradia assistida e "
            "leito/regime fechado — e não somada num só número. Fundir as onze "
            "classificações do 115 mediria como equivalentes serviços que a "
            "política pública trata como opostos. O total conta "
            "estabelecimentos distintos, então NÃO é a soma dos três. O "
            "agrupamento em três é decisão editorial deste observatório, não "
            "classificação oficial do Ministério da Saúde.")
        com_psicologo = sum(d.get("municipios_com_psicologo") or 0
                            for d in ufs.values())
        total_mun = sum(d.get("municipios_total") or 0 for d in ufs.values())
        itens.append(
            f"A cobertura por força de trabalho está quase saturada: "
            f"{com_psicologo} dos {total_mun} municípios têm psicólogo "
            "vinculado ao SUS. O ICAP continua medindo diferença real — há "
            "estado com um em cada oito municípios sem nenhum psicólogo — mas "
            "separa pouco. Quem quiser comparar a densidade das redes deve "
            "olhar psicólogos por 100 mil habitantes, que varia bem mais.")
    else:
        itens.append("A base do CNES não foi lida; a cobertura assistencial de "
                     "saúde está nula, não zerada.")

    if suas:
        itens.append(
            "Não existe contagem de psicólogos no SUAS. O CadSUAS publica total "
            "de profissionais por unidade, sem abertura por ocupação — não há "
            "equivalente do CBO do CNES. A cobertura socioassistencial mede "
            "presença de CREAS, não presença de psicólogo nele.")
        itens.append(
            f"O CRAS existe em {suas['metadados'].get('municipios_com_cras')} "
            f"dos {suas['metadados'].get('municipios_lidos')} municípios. Uma "
            "fração que vale praticamente 1 em toda UF não ordena nada, então "
            "o CRAS é publicado como contagem e densidade, e só o CREAS vira "
            "índice de cobertura.")
        itens.append(
            "A fonte socioassistencial é o CadSUAS pela API MI Social da SAGI, "
            "não o microdado do Censo SUAS: em setembro de 2026 o catálogo de "
            "microdados da SAGI responde com aviso de indisponibilidade por "
            "restrição de período eleitoral, e o conjunto CadSUAS no Portal "
            "Brasileiro de Dados Abertos exige chave de API.")
    else:
        itens.append("O CadSUAS não foi lido; a cobertura socioassistencial "
                     "está nula, não zerada.")

    return itens


def proveniencia(bruto, qualidade, cobertura, suas, ufs):
    fontes = {
        "censo": {
            "presente": True,
            **(bruto["metadados"].get("proveniencia_censo") or {}),
        },
        "cpc": ({"presente": True, **qualidade["metadados"]} if qualidade
                else {"presente": False,
                      "motivo": "data/qualidade.json não gerado"}),
        "cnes": ({"presente": True, **cobertura["metadados"]} if cobertura
                 else {"presente": False,
                       "motivo": "data/cobertura_cnes.json não gerado"}),
        "cadsuas": ({"presente": True, **suas["metadados"]} if suas
                    else {"presente": False,
                          "motivo": "data/cobertura_suas.json não gerado"}),
        # As fontes do IBGE também declaram `presente`, como as demais. Sem o
        # campo, ficariam de fora de qualquer varredura que pergunte "quais
        # fontes faltaram?" — e uma fonte que nunca aparece na resposta é uma
        # fonte que ninguém percebe ter sumido.
        "ibge_municipios": {"presente": True,
                            **(bruto["metadados"].get("municipios_ibge") or {})},
        "ibge_populacao": {"presente": True,
                           **(bruto["metadados"].get("populacao_ibge") or {})},
    }
    return {
        "gerado_em": date.today().isoformat(),
        "fontes": fontes,
        "limitacoes_conhecidas": limitacoes(ufs, qualidade, cobertura, suas),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bruto", default=str(DATA / "bruto.json"))
    p.add_argument("--qualidade", default=str(DATA / "qualidade.json"))
    p.add_argument("--cobertura", default=str(DATA / "cobertura_cnes.json"))
    p.add_argument("--suas", default=str(DATA / "cobertura_suas.json"))
    p.add_argument("--saida", default=str(DATA / "nacional.json"))
    args = p.parse_args()

    bruto = _ler(args.bruto)
    qualidade = _ler(args.qualidade, obrigatorio=False)
    cobertura = _ler(args.cobertura, obrigatorio=False)
    suas = _ler(args.suas, obrigatorio=False)

    ufs = bruto["ufs"]
    municipios = bruto["municipios"]

    juntar_qualidade(ufs, qualidade)
    juntar_cobertura(ufs, municipios, cobertura)
    juntar_suas(ufs, municipios, suas)
    aplicar(ufs)

    metadados = dict(bruto["metadados"])
    metadados["proveniencia"] = proveniencia(bruto, qualidade, cobertura, suas, ufs)
    nacional = {"metadados": metadados, "ufs": ufs}

    Path(args.saida).write_text(
        json.dumps(nacional, ensure_ascii=False, indent=1), encoding="utf-8")
    campos = len(next(iter(ufs.values())))
    print(f"[CONSOLIDAR] {len(ufs)} UFs, {campos} campos por UF -> {args.saida}")

    destino_mun = DATA / "municipios"
    destino_mun.mkdir(parents=True, exist_ok=True)
    total = 0
    for uf, lista in municipios.items():
        (destino_mun / f"{uf}.json").write_text(
            json.dumps({"uf": uf, "municipios": lista},
                       ensure_ascii=False, indent=1), encoding="utf-8")
        total += len(lista)
    print(f"[CONSOLIDAR] {total} municípios em {len(municipios)} arquivos "
          f"-> {destino_mun}")

    (DATA / "_proveniencia.json").write_text(
        json.dumps(metadados["proveniencia"], ensure_ascii=False, indent=2),
        encoding="utf-8")
    print("[CONSOLIDAR] proveniência -> data/_proveniencia.json")

    faltando = [n for n, f in metadados["proveniencia"]["fontes"].items()
                if isinstance(f, dict) and f.get("presente") is False]
    if faltando:
        print(f"[CONSOLIDAR] ATENÇÃO: fontes ausentes: {faltando}. "
              "Os indicadores correspondentes estão nulos, não zerados.")


if __name__ == "__main__":
    main()
