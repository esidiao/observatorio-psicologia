"""
etl/serie.py
Série histórica: compara edições do Censo da Educação Superior.

Uso:
    python etl/serie.py --anos 2023 2024
    python etl/serie.py --anos 2021 2022 2023 2024

Saída: data/serie.json  (Brasil e por UF, só com campos comparáveis)

POR QUE DÁ PARA VOLTAR NO TEMPO SEM GAMBIARRA
----------------------------------------------
O INEP reclassificou as edições antigas na CINE e as republicou, então
`NO_CINE_ROTULO` existe em todas — e o match EXATO de rótulo, que é a regra do
projeto inteiro, vale para trás sem adaptação. Aqui ele é indispensável:
`Psicopedagogia` tem 6.083 registros contra 1.372 de `Psicologia`, e uma
substring inverteria a série inteira.

O TOTAL NACIONAL DE IES NÃO É A SOMA DAS UFs
---------------------------------------------
Uma instituição que oferta em três estados aparece nas três contagens
estaduais. Somá-las devolve 1.068 para o Censo 2024, contra 1.032 distintas —
e a home publica 1.032, lido do mesmo arquivo. Duas páginas do mesmo site com
números diferentes para a mesma coisa é pior que um número errado sozinho.

Por isso o conjunto nacional de códigos de IES é contado durante a LEITURA,
quando os códigos ainda estão à mão, e guardado no cache do ano. Os demais
campos somam sem problema: município pertence a uma UF só.

POUCOS CAMPOS, DE PROPÓSITO
---------------------------
A série guarda apenas o que é comparável entre edições. Campos de perfil e
qualidade mudam de definição, de cobertura e até de existência entre anos; um
gráfico que os empilha lado a lado descreve mudança de metodologia como se
fosse mudança do mundo. O que sobra — vagas, matrículas, concluintes,
municípios com oferta, polos, IES — mantém o mesmo significado.

CADA ANO É LIDO E DESCARTADO
-----------------------------
O ZIP de cada edição é lido remotamente por intervalo de bytes, agregado, e o
agregado (poucos KB) é o que fica em disco. Guardar os cadastros completos de
quatro edições custaria mais de um giga para produzir um arquivo de 60 KB.
"""
import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extrair_censo import URL_CENSO, normalizar  # noqa: E402
from rede import ZipRemotoHTTP, sondar  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
DADOS = REPO / "etl" / "dados"
DATA = REPO / "data"

DIM_PRESENCIAL, DIM_POLO, DIM_SEDE = "1", "2", "3"

# Campos que significam a mesma coisa em todas as edições.
CAMPOS = [
    "vagas_presencial", "vagas_ead", "vagas_total",
    "n_cursos_presencial", "n_ies",
    "municipios_oferta", "ead_polos_registros", "ead_polos_municipios",
    "matriculas", "concluintes",
]

csv.field_size_limit(1 << 24)


def inteiro(valor):
    texto = (valor or "").strip()
    return int(texto) if texto.lstrip("-").isdigit() else 0


def agregar_ano(ano, rotulo="Psicologia"):
    """Lê a edição `ano` remotamente e devolve o agregado por UF."""
    cache = DADOS / f"serie_{ano}.json"
    if cache.exists():
        print(f"[SERIE] {ano}: usando agregado em cache")
        guardado = json.loads(cache.read_text(encoding="utf-8"))
        # Formato antigo: o cache era o mapa de UFs direto, sem bloco nacional.
        # Aceitá-lo é preciso — apagar caches bons custaria uma releitura de
        # 400 MB por ano — mas ele não tem como informar o total distinto, e
        # nesse caso o total sai nulo em vez de sair errado.
        if "ufs" not in guardado:
            return {"ufs": guardado, "brasil": None}
        return guardado

    url = URL_CENSO.format(ano=ano)
    existe, detalhe = sondar(url)
    if existe is False:
        print(f"[SERIE] {ano}: confirmadamente não publicado — ano pulado.")
        return None
    if existe is None:
        print(f"[SERIE] {ano}: INDETERMINADO ({detalhe}). "
              "Ano pulado sem afirmar que não existe.")
        return None

    z = ZipRemotoHTTP(url)
    alvo = z.localizar("cadastro_cursos", ".csv") or z.localizar("curso", ".csv")
    alvo_ies = z.localizar("_ies_", ".csv") or z.localizar("ies", ".csv")
    if not alvo or not alvo_ies:
        print(f"[SERIE] {ano}: membros esperados não encontrados no ZIP — pulado.")
        return None

    print(f"[SERIE] {ano}: lendo {alvo.rsplit('/', 1)[-1]} ...")

    uf_sede = {}
    with z.membro_arquivo(alvo_ies) as f:
        for linha in csv.DictReader(f, delimiter=";"):
            codigo = (linha.get("CO_IES") or "").strip()
            sigla = (linha.get("SG_UF_IES") or "").strip().upper()
            if codigo and sigla:
                uf_sede[codigo] = sigla

    alvo_norm = normalizar(rotulo)
    ies_do_pais = set()
    ufs = defaultdict(lambda: {
        "vagas_presencial": 0, "vagas_ead": 0, "n_cursos_presencial": 0,
        "ead_polos_registros": 0, "matriculas": 0, "concluintes": 0,
        "_ies": set(), "_mun_oferta": set(), "_mun_polo": set(),
    })
    lidas = casadas = 0

    with z.membro_arquivo(alvo) as f:
        for linha in csv.DictReader(f, delimiter=";"):
            lidas += 1
            if normalizar(linha.get("NO_CINE_ROTULO")) != alvo_norm:
                continue
            casadas += 1
            dimensao = (linha.get("TP_DIMENSAO") or "").strip()
            cod_ies = (linha.get("CO_IES") or "").strip()
            sigla = (linha.get("SG_UF") or "").strip().upper() or None
            vagas = inteiro(linha.get("QT_VG_TOTAL"))
            cod_mun = (linha.get("CO_MUNICIPIO") or "").strip()

            if dimensao == DIM_SEDE:
                sigla = uf_sede.get(cod_ies)
            if not sigla:
                continue
            ies_do_pais.add(cod_ies)
            d = ufs[sigla]
            d["_ies"].add(cod_ies)
            d["matriculas"] += inteiro(linha.get("QT_MAT"))
            d["concluintes"] += inteiro(linha.get("QT_CONC"))

            if dimensao == DIM_PRESENCIAL:
                d["vagas_presencial"] += vagas
                d["n_cursos_presencial"] += 1
                d["_mun_oferta"].add(cod_mun)
            elif dimensao == DIM_SEDE:
                d["vagas_ead"] += vagas
            elif dimensao == DIM_POLO:
                d["ead_polos_registros"] += 1
                d["_mun_polo"].add(cod_mun)

    saida = {}
    for sigla, d in ufs.items():
        saida[sigla] = {
            "vagas_presencial": d["vagas_presencial"],
            "vagas_ead": d["vagas_ead"],
            "vagas_total": d["vagas_presencial"] + d["vagas_ead"],
            "n_cursos_presencial": d["n_cursos_presencial"],
            "n_ies": len(d["_ies"]),
            "municipios_oferta": len(d["_mun_oferta"]),
            "ead_polos_registros": d["ead_polos_registros"],
            "ead_polos_municipios": len(d["_mun_polo"]),
            "matriculas": d["matriculas"],
            "concluintes": d["concluintes"],
        }

    agregado = {"ufs": saida, "brasil": {"n_ies": len(ies_do_pais)}}
    print(f"[SERIE] {ano}: {lidas} linhas, {casadas} do rótulo exato, "
          f"{len(saida)} UFs, {len(ies_do_pais)} IES distintas no país")
    DADOS.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(agregado, ensure_ascii=False, indent=1),
                     encoding="utf-8")
    return agregado


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--anos", nargs="+", type=int, default=[2023, 2024])
    p.add_argument("--rotulo", default="Psicologia")
    p.add_argument("--saida", default=str(DATA / "serie.json"))
    args = p.parse_args()

    por_ano, nacional_por_ano = {}, {}
    for ano in sorted(args.anos):
        agregado = agregar_ano(ano, args.rotulo)
        if agregado and agregado["ufs"]:
            por_ano[str(ano)] = agregado["ufs"]
            nacional_por_ano[str(ano)] = agregado["brasil"]

    if len(por_ano) < 2:
        raise SystemExit(
            "[SERIE] menos de duas edições disponíveis; a série não é gerada. "
            "Uma série de um ponto não é série, e publicar uma seria sugerir "
            "comparação onde não há.")

    anos = sorted(por_ano)
    siglas = sorted({s for ano in anos for s in por_ano[ano]})

    ufs = {}
    for sigla in siglas:
        ufs[sigla] = {ano: por_ano[ano].get(sigla) for ano in anos}

    brasil = {}
    sem_total_distinto = []
    for ano in anos:
        brasil[ano] = {campo: sum((por_ano[ano].get(s) or {}).get(campo) or 0
                                  for s in siglas)
                       for campo in CAMPOS}
        # `n_ies` é o único campo em que a soma das UFs não é o total do país:
        # uma instituição que oferta em três estados entra em três contagens.
        # Vem do conjunto nacional, ou fica nulo — nunca a soma.
        distinto = (nacional_por_ano.get(ano) or {}).get("n_ies")
        brasil[ano]["n_ies"] = distinto
        if distinto is None:
            sem_total_distinto.append(ano)
    if sem_total_distinto:
        print(f"[SERIE] atenção: {', '.join(sem_total_distinto)} vieram de "
              "cache antigo, sem o conjunto nacional de IES. O total do país "
              "fica NULO nesses anos — a soma das UFs contaria em dobro quem "
              "oferta em mais de um estado. Apague etl/dados/serie_<ano>.json "
              "e rode de novo para preencher.")

    saida = {
        "metadados": {
            "fonte": "Censo da Educação Superior (INEP)",
            "curso": args.rotulo,
            "match": "igualdade sobre o rótulo CINE normalizado",
            "observacao": (
                "Somente campos com significado estável entre edições. Campos "
                "de perfil e qualidade mudam de definição entre anos e não "
                "entram na série."
            ),
            "n_ies_no_brasil": (
                "Instituições DISTINTAS no país, contadas sobre o conjunto "
                "nacional de códigos — não a soma das contagens estaduais, que "
                "conta em dobro quem oferta em mais de um estado."
            ),
            "gerado_em": date.today().isoformat(),
        },
        "anos": anos,
        "campos": CAMPOS,
        "brasil": brasil,
        "ufs": ufs,
    }
    Path(args.saida).parent.mkdir(parents=True, exist_ok=True)
    Path(args.saida).write_text(json.dumps(saida, ensure_ascii=False, indent=1),
                                encoding="utf-8")
    print(f"[SERIE] {len(anos)} edições ({', '.join(anos)}) -> {args.saida}")
    for campo in ("vagas_total", "matriculas", "concluintes"):
        antes, depois = brasil[anos[0]][campo], brasil[anos[-1]][campo]
        variacao = (depois - antes) / antes * 100 if antes else None
        marca = f"{variacao:+.1f}%" if variacao is not None else "—"
        print(f"[SERIE]   {campo}: {antes} -> {depois} ({marca})")


if __name__ == "__main__":
    main()
