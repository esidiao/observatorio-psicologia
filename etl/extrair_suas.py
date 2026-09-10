"""
etl/extrair_suas.py
Extrai do SUAS a rede socioassistencial municipal — CRAS e CREAS — pela API
MI Social da SAGI/MDS.

Uso:
    python etl/extrair_suas.py
    python etl/extrair_suas.py --anomes 202608
    python etl/extrair_suas.py --listar        # períodos com dado de CadSUAS

Saída: data/cobertura_suas.json — por município.

POR QUE ESTA FONTE ESTÁ AQUI
-----------------------------
O psicólogo é equipe de referência obrigatória em CRAS e CREAS. Psicologia é
das pouquíssimas formações cuja absorção pelo poder público se reparte entre
DUAS políticas nacionais — saúde e assistência social — e medir só o CNES
descreveria metade do destino de quem se forma. É isto que distingue este
observatório dos irmãos.

DE ONDE VEM, E POR QUE NÃO É O MICRODADO DO CENSO SUAS
-------------------------------------------------------
O caminho óbvio seria o microdado do Censo SUAS, publicado anualmente pelo MDS.
Ele não serviu: em setembro de 2026 o catálogo de microdados da SAGI
(`aplicacoes.mds.gov.br/sagicad/pesquisas/pes-metadados.php`) responde com aviso
de indisponibilidade por restrição de período eleitoral, e o Portal Brasileiro
de Dados Abertos exige chave de API (401) para o conjunto CadSUAS.

O que existe, público e legível por máquina, é a API MI Social da SAGI, que
publica o CadSUAS agregado por município. É dela que este extrator lê. A
diferença é declarada na proveniência: o dado é o CADASTRO das unidades
(CadSUAS), não o questionário do Censo SUAS.

O QUE DÁ PARA MEDIR — E O QUE NÃO DÁ
-------------------------------------
Dá para medir a EXISTÊNCIA e a QUANTIDADE de CRAS e CREAS por município, e o
total de profissionais lotados neles.

NÃO dá para contar psicólogos no SUAS. `cadsuas_qtd_profissionais_cras_i` conta
trabalhadores, sem abertura por ocupação — não há equivalente do CBO do CNES.
Publicar "psicólogos no SUAS" a partir daqui exigiria aplicar a equipe mínima
da NOB-RH/SUAS como se fosse contagem, o que é estimativa disfarçada de
medição. O indicador não existe, e não foi substituído por aproximação.

CRAS É QUASE UNIVERSAL, E ISSO MUDA O INDICADOR
------------------------------------------------
Medido em 202608: 5.559 dos 5.571 municípios têm ao menos um CRAS — 99,8%. Uma
fração que vale praticamente 1 em toda UF não ordena nada, e transformá-la em
índice de cobertura produziria um ranking de ruído. Por isso o CRAS é publicado
como CONTAGEM e como DENSIDADE por 100 mil habitantes, onde a variação é real,
e não como fração de municípios cobertos.

O CREAS é outra história: 2.758 municípios, 49,5%. Aí a fração cobre território
de verdade, varia entre estados, e vira índice.
"""
import argparse
import json
import sys
import urllib.parse
from collections import defaultdict
from datetime import date
from pathlib import Path

from rede import ler_json, sondar

REPO = Path(__file__).parent.parent
DATA = REPO / "data"

BASE = "https://aplicacoes.mds.gov.br/sagi/servicos/misocial"

# Campos pedidos à API. Nomeados uma vez só: repetir a lista nas duas pontas
# (pedido e leitura) foi o que fez um campo sumir do conjunto em vez de sair
# nulo, no projeto de Farmácia — e campo ausente não aparece como "sem dados",
# some da página inteira sem alarme nenhum.
CAMPOS = {
    "codigo_ibge": "codigo_ibge",
    "municipio": "municipio",
    "cras": "cadsuas_qtd_cras_i",
    "creas": "cadsuas_qtd_creas_i",
    "profissionais_cras": "cadsuas_qtd_profissionais_cras_i",
    "profissionais_creas": "cadsuas_qtd_profissionais_creas_i",
    "extracao": "cadsuas_data_extracao_s",
}

UF_POR_CODIGO = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP",
    "17": "TO", "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB",
    "26": "PE", "27": "AL", "28": "SE", "29": "BA", "31": "MG", "32": "ES",
    "33": "RJ", "35": "SP", "41": "PR", "42": "SC", "43": "RS", "50": "MS",
    "51": "MT", "52": "GO", "53": "DF",
}

# Abaixo disto, a leitura não cobriu o país e não deve virar indicador: uma
# cobertura parcial lida como total transforma município não lido em município
# sem CRAS, que é uma afirmação forte e falsa.
MINIMO_MUNICIPIOS = 5000


def _consultar(**parametros):
    parametros.setdefault("wt", "json")
    return ler_json(BASE + "?" + urllib.parse.urlencode(parametros))


def periodos_disponiveis():
    """Períodos (AAAAMM) em que o CadSUAS tem contagem de CRAS, do mais antigo."""
    r = _consultar(**{
        "q": "cadsuas_qtd_cras_i:[1 TO *]", "rows": "0", "facet": "true",
        "facet.field": "anomes", "facet.limit": "-1", "facet.sort": "index",
    })
    bruto = r["facet_counts"]["facet_fields"]["anomes"]
    return [(a, c) for a, c in zip(bruto[0::2], bruto[1::2]) if c]


def extrair(anomes):
    """Lê o país inteiro de uma vez. São 5.571 linhas e poucos campos."""
    r = _consultar(**{
        "q": f"anomes:{anomes}",
        "rows": "6000",
        "fl": ",".join(CAMPOS.values()),
    })
    docs = r["response"]["docs"]
    achados = r["response"]["numFound"]
    if len(docs) < achados:
        raise SystemExit(
            f"[ERRO] a API devolveu {len(docs)} de {achados} municípios. "
            "Leitura parcial lida como total viraria 'município sem CRAS' — "
            "aumente `rows` em vez de publicar o recorte.")
    if len(docs) < MINIMO_MUNICIPIOS:
        raise SystemExit(
            f"[ERRO] só {len(docs)} municípios em {anomes}; abaixo do mínimo "
            f"de {MINIMO_MUNICIPIOS}. Período incompleto não vira indicador.")
    return docs


def montar(anomes, docs):
    municipios = {}
    extracoes = set()
    for d in docs:
        codigo = str(d.get(CAMPOS["codigo_ibge"]) or "").strip()
        if not codigo:
            continue
        extracao = d.get(CAMPOS["extracao"])
        if extracao:
            extracoes.add(extracao)
        cras = d.get(CAMPOS["cras"])
        creas = d.get(CAMPOS["creas"])
        # Zero é MEDIDA aqui, não ausência: a API devolve linha para os 5.571
        # municípios, então "0 CREAS" quer dizer que o município foi lido e não
        # tem CREAS. Trocar isso por None apagaria metade do achado — são 2.813
        # municípios sem CREAS nenhum, que é o número que interessa.
        municipios[codigo] = {
            "cras": int(cras) if cras is not None else None,
            "creas": int(creas) if creas is not None else None,
            "profissionais_cras": d.get(CAMPOS["profissionais_cras"]),
            "profissionais_creas": d.get(CAMPOS["profissionais_creas"]),
        }

    com_cras = sum(1 for m in municipios.values() if m["cras"])
    com_creas = sum(1 for m in municipios.values() if m["creas"])
    return {
        "metadados": {
            "fonte": "CadSUAS, pela API MI Social (SAGI/MDS)",
            "url": f"{BASE}?q=anomes:{anomes}",
            "anomes": anomes,                  # do DADO, não do calendário
            "data_extracao_declarada_pela_fonte": sorted(extracoes) or None,
            "municipios_lidos": len(municipios),
            "municipios_com_cras": com_cras,
            "municipios_com_creas": com_creas,
            "cras_total": sum(m["cras"] or 0 for m in municipios.values()),
            "creas_total": sum(m["creas"] or 0 for m in municipios.values()),
            "por_que_nao_o_censo_suas": (
                "O microdado do Censo SUAS não foi usado porque o catálogo da "
                "SAGI responde, em setembro de 2026, com aviso de "
                "indisponibilidade por restrição de período eleitoral, e o "
                "conjunto CadSUAS no Portal Brasileiro de Dados Abertos exige "
                "chave de API (401). A API MI Social publica o mesmo cadastro "
                "agregado por município, e é pública."
            ),
            "psicologos_no_suas_indisponivel": (
                "Não há contagem de psicólogos no SUAS. O CadSUAS publica "
                "total de profissionais por unidade, sem abertura por "
                "ocupação — não existe equivalente do CBO do CNES. Derivar a "
                "contagem da equipe mínima da NOB-RH/SUAS seria estimativa "
                "disfarçada de medição. O indicador não existe e não foi "
                "substituído por aproximação."
            ),
            "cras_nao_vira_indice_de_cobertura": (
                f"{com_cras} dos {len(municipios)} municípios têm ao menos um "
                "CRAS. Uma fração que vale praticamente 1 em toda UF não "
                "ordena nada, então o CRAS é publicado como contagem e como "
                "densidade por 100 mil habitantes. O CREAS, presente em "
                f"{com_creas} municípios, vira índice de cobertura."
            ),
            "extraido_em": date.today().isoformat(),
        },
        "municipios": municipios,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--anomes", help="AAAAMM; default: o mais recente com dado")
    p.add_argument("--listar", action="store_true",
                   help="lista os períodos com dado de CadSUAS e sai")
    p.add_argument("--saida", default=str(DATA / "cobertura_suas.json"))
    args = p.parse_args()

    existe, detalhe = sondar(BASE)
    if existe is False:
        raise SystemExit(f"[ERRO] {BASE} confirmadamente ausente (404).")
    if existe is None:
        raise SystemExit(
            f"[ERRO] não foi possível verificar {BASE} ({detalhe}). "
            "Indeterminado não é ausente — tente de novo em vez de publicar "
            "a cobertura socioassistencial como nula.")

    periodos = periodos_disponiveis()
    if args.listar:
        print(f"{len(periodos)} períodos com contagem de CRAS")
        for anomes, n in periodos[-12:]:
            print(f"  {anomes}: {n} municípios")
        return
    if not periodos:
        raise SystemExit("[ERRO] nenhum período com contagem de CRAS na API.")

    anomes = args.anomes or periodos[-1][0]
    print(f"[SUAS] período: {anomes}")

    docs = extrair(anomes)
    saida = montar(anomes, docs)
    m = saida["metadados"]
    print(f"[SUAS] {m['municipios_lidos']} municípios lidos")
    print(f"[SUAS] CRAS: {m['cras_total']} em {m['municipios_com_cras']} municípios")
    print(f"[SUAS] CREAS: {m['creas_total']} em {m['municipios_com_creas']} municípios")
    print(f"[SUAS] extração declarada pela fonte: "
          f"{m['data_extracao_declarada_pela_fonte']}")

    Path(args.saida).parent.mkdir(parents=True, exist_ok=True)
    Path(args.saida).write_text(
        json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[SUAS] -> {args.saida}")


if __name__ == "__main__":
    sys.exit(main())
