"""
tests/test_validacao.py
Integridade do conjunto publicado, contra âncoras conhecidas.

As âncoras foram apuradas no Censo 2024, no CPC 2022, no CNES 202607 e no
CadSUAS 202608, lendo os arquivos originais. Servem como teste de REGRESSÃO: se
o pipeline passar a produzir outra coisa, o mais provável é defeito no
pipeline, não notícia nos dados. Uma edição nova das fontes muda os números de
propósito — e aí estas constantes mudam junto, num commit que diz isso.

Roda como script ou sob pytest.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"

CENSO = 2024
CICLO_CPC = "2022"
COMPETENCIA_CNES = "202607"
ANOMES_SUAS = "202608"

# ------------------------------------------------------- âncoras: Censo 2024
REGISTROS_CENSO = 1372
UFS_COM_PRESENCIAL = 27
MUNICIPIOS_COM_OFERTA = 498
CURSOS_PRESENCIAIS = 1256
VAGAS_PRESENCIAL = 276250
VAGAS_EAD = 549
POLOS_REGISTROS = 114
POLOS_MUNICIPIOS = 105
MATRICULAS = 375574
CONCLUINTES = 49065
IES_DISTINTAS = 1032

# A EaD como fato estrutural, medido em UFs e não em vagas.
UFS_SEM_VAGA_EAD = 25
UFS_SEM_POLO = ["AC", "AP", "RO", "RR"]
PCT_EAD_MAXIMO = 1.0          # participação nacional da EaD, em %

# --------------------------------------------------------- âncoras: CPC 2022
CURSOS_AVALIADOS = 746
UFS_AVALIADAS = 27
CURSOS_COM_CPC = 740
CURSOS_COM_IDD = 746
CONCLUINTES_PARTICIPANTES = 39135

# -------------------------------------------------------- âncoras: CadSUAS
CRAS_TOTAL = 8977
CREAS_TOTAL = 3039
MUNICIPIOS_COM_CRAS = 5559
MUNICIPIOS_COM_CREAS = 2758

MUNICIPIOS_BRASIL = 5571          # IBGE, desde a instalação de Boa Esperança
MUNICIPIOS_MT = 142               # do Norte (MT) em 01/01/2025

SUBGRUPOS_RAPS = ("comunitaria", "residencial", "internacao")


def _ler(nome):
    caminho = DATA / nome
    if not caminho.exists():
        raise SystemExit(
            f"[ERRO] {caminho} ausente. Rode o pipeline antes dos testes.")
    return json.loads(caminho.read_text(encoding="utf-8"))


def _soma(ufs, campo):
    return sum(d.get(campo) or 0 for d in ufs.values())


# ------------------------------------------------------------------ território

def test_27_ufs_presentes():
    ufs = _ler("nacional.json")["ufs"]
    assert len(ufs) == 27, f"esperado 27 UFs, veio {len(ufs)}"


def test_todas_as_ufs_tem_oferta_presencial():
    """
    Psicologia é ofertada nas 27 unidades da federação.

    É um fato do curso, não um acaso da edição: nos observatórios irmãos há
    estados sem oferta, e a página tem texto próprio para eles. Se este teste
    falhar, ou o Censo mudou ou o filtro de rótulo capturou/perdeu linhas.
    """
    ufs = _ler("nacional.json")["ufs"]
    sem = sorted(u for u, d in ufs.items() if not d.get("tem_oferta_presencial"))
    assert not sem, f"UFs sem oferta presencial: {sem} — esperado nenhuma"
    com = [u for u, d in ufs.items() if d.get("tem_oferta_presencial")]
    assert len(com) == UFS_COM_PRESENCIAL


def test_contagem_de_municipios_do_ibge():
    ufs = _ler("nacional.json")["ufs"]
    total = _soma(ufs, "municipios_total")
    assert total == MUNICIPIOS_BRASIL, (
        f"esperado {MUNICIPIOS_BRASIL} municípios, veio {total}. "
        "Se o IBGE instalou ou extinguiu município, a mudança é real — "
        "atualize a âncora num commit que explique.")
    assert ufs["MT"]["municipios_total"] == MUNICIPIOS_MT, (
        f"MT deveria ter {MUNICIPIOS_MT} municípios, "
        f"veio {ufs['MT']['municipios_total']}")


def test_municipios_com_oferta():
    ufs = _ler("nacional.json")["ufs"]
    total = _soma(ufs, "municipios_oferta")
    assert total == MUNICIPIOS_COM_OFERTA, (
        f"esperado {MUNICIPIOS_COM_OFERTA}, veio {total}")


# ------------------------------------------------------------------ capacidade

def test_vagas_presenciais_e_ead():
    """
    As duas camadas da EaD somadas separadamente.

    Somar QT_VG_TOTAL por SG_UF sem separar sede de polo devolve vagas EaD
    zeradas. Em Psicologia isso é MAIS fácil de passar despercebido, não menos:
    549 é um número pequeno o bastante para ninguém conferir, e é exatamente
    por isso que ele está aqui como âncora.
    """
    ufs = _ler("nacional.json")["ufs"]
    presencial = _soma(ufs, "vagas_presencial")
    ead = _soma(ufs, "vagas_ead")
    assert presencial == VAGAS_PRESENCIAL, (
        f"vagas presenciais: esperado {VAGAS_PRESENCIAL}, veio {presencial}")
    assert ead == VAGAS_EAD, f"vagas EaD: esperado {VAGAS_EAD}, veio {ead}"
    assert ead > 0, ("vagas EaD zeradas — sintoma clássico de somar as linhas "
                     "de polo em vez das de sede")


def test_cursos_e_ies():
    ufs = _ler("nacional.json")["ufs"]
    assert _soma(ufs, "n_cursos_presencial") == CURSOS_PRESENCIAIS


def test_polos_ead():
    ufs = _ler("nacional.json")["ufs"]
    assert _soma(ufs, "ead_polos_registros") == POLOS_REGISTROS
    assert _soma(ufs, "ead_polos_municipios") == POLOS_MUNICIPIOS


def test_fluxo():
    ufs = _ler("nacional.json")["ufs"]
    assert _soma(ufs, "matriculas") == MATRICULAS, (
        f"matrículas: esperado {MATRICULAS}, veio {_soma(ufs, 'matriculas')}")
    assert _soma(ufs, "concluintes") == CONCLUINTES


def test_concentracao_calculada_sobre_a_capacidade_total():
    """
    HHI existe para toda UF com vagas, e fica em 0..1.

    Nos observatórios com EaD grande, este teste também exigia que o HHI de
    mantenedora fosse bem maior que o de IES — era assim que se detectava um
    cálculo feito só sobre o presencial. Aqui essa checagem não vale: com a EaD
    em 0,2% da capacidade, os dois índices coincidem por motivo legítimo, e
    exigir distância entre eles reprovaria o resultado correto.
    """
    ufs = _ler("nacional.json")["ufs"]
    for sigla, d in ufs.items():
        if d["vagas_total"]:
            assert d["HHI"] is not None, f"{sigla} com vagas mas sem HHI"
            assert 0 <= d["HHI"] <= 1, f"{sigla}: HHI fora de 0..1"
            assert d["HHI_mantenedora"] is not None, (
                f"{sigla} com vagas mas sem HHI de mantenedora")


# ----------------------------------------------- o fato estrutural: é presencial

def test_ead_quase_nao_existe():
    ufs = _ler("nacional.json")["ufs"]
    total = _soma(ufs, "vagas_presencial") + _soma(ufs, "vagas_ead")
    pct = 100 * _soma(ufs, "vagas_ead") / total
    assert pct < PCT_EAD_MAXIMO, (
        f"participação da EaD em {pct:.2f}% — acima do teto de "
        f"{PCT_EAD_MAXIMO}%. Se a modalidade cresceu de verdade, é notícia e a "
        "âncora muda; se não, o tratamento sede/polo quebrou.")


def test_zero_de_ead_e_medida_nao_ausencia():
    """
    O teste central deste observatório.

    Vinte e cinco UFs não têm nenhuma vaga a distância. Esse valor precisa ser
    `0` — medida —, jamais `None`. Trocar por None faria o site dizer "sem
    dados" onde há dado, e o achado que distingue Psicologia dos cursos irmãos
    desapareceria disfarçado de lacuna.

    O contrário — 0 no lugar de ausência — é vigiado por
    `test_ausencia_nunca_e_zero`. As duas direções importam.
    """
    ufs = _ler("nacional.json")["ufs"]
    zeros = [u for u, d in ufs.items() if d.get("vagas_ead") == 0]
    nulos = [u for u, d in ufs.items() if d.get("vagas_ead") is None]
    assert not nulos, (
        f"UFs com vagas_ead nulo: {nulos}. O Censo foi lido para as 27 UFs, "
        "então a ausência de vaga EaD é zero medido, não dado faltante.")
    assert len(zeros) == UFS_SEM_VAGA_EAD, (
        f"esperado {UFS_SEM_VAGA_EAD} UFs com zero vagas EaD, veio {len(zeros)}")

    sem_polo = sorted(u for u, d in ufs.items()
                      if d.get("ead_polos_registros") == 0)
    assert sem_polo == UFS_SEM_POLO, (
        f"esperado {UFS_SEM_POLO} sem nenhum polo, veio {sem_polo}")


# ------------------------------------------------------------------- qualidade

def test_qualidade_cpc():
    q = _ler("qualidade.json")
    assert q["metadados"]["ciclo"] == CICLO_CPC, (
        f"ciclo {q['metadados']['ciclo']}, esperado {CICLO_CPC}. Psicologia "
        "não está no CPC 2023 — aquele é o ciclo da saúde e das engenharias.")
    assert len(q["cursos"]) == CURSOS_AVALIADOS, (
        f"esperado {CURSOS_AVALIADOS} cursos avaliados, veio {len(q['cursos'])}")
    assert len(q["ufs"]) == UFS_AVALIADAS
    com_cpc = sum(1 for c in q["cursos"] if c["CPC_cont"] is not None)
    com_idd = sum(1 for c in q["cursos"] if c["IDD"] is not None)
    assert com_cpc == CURSOS_COM_CPC, f"com CPC: esperado {CURSOS_COM_CPC}, veio {com_cpc}"
    assert com_idd == CURSOS_COM_IDD, f"com IDD: esperado {CURSOS_COM_IDD}, veio {com_idd}"
    participantes = sum(c["concluintes_participantes"] or 0 for c in q["cursos"])
    assert participantes == CONCLUINTES_PARTICIPANTES


def test_todos_os_cursos_avaliados_sao_presenciais():
    """
    Nenhum curso EaD de Psicologia foi avaliado no ciclo 2022 — nenhum mesmo.

    Não é filtro deste projeto: é o que a planilha do INEP traz. Se algum dia
    aparecer curso a distância aqui, é mudança real do ensino da Psicologia no
    país, e merece um commit que diga isso em vez de passar batido.
    """
    q = _ler("qualidade.json")
    modalidades = {(c.get("modalidade") or "").strip() for c in q["cursos"]}
    assert len(modalidades) == 1, (
        f"esperada uma única modalidade entre os cursos avaliados, "
        f"vieram {sorted(modalidades)}")
    assert "distância" not in next(iter(modalidades)).lower()


def test_toda_uf_tem_curso_avaliado():
    ufs = _ler("nacional.json")["ufs"]
    sem = sorted(u for u, d in ufs.items() if not d.get("tem_avaliacao"))
    assert not sem, (
        f"UFs sem curso avaliado: {sem}. No ciclo 2022 a cobertura é total; "
        "se deixou de ser, os indicadores de qualidade delas ficam nulos e "
        "esta âncora muda junto.")


# ------------------------------------------------------------------- cobertura

def test_tres_coberturas_existem_e_sao_separadas():
    ufs = _ler("nacional.json")["ufs"]
    for indice in ("ICAP", "ICRP", "ICAS"):
        faltando = [u for u, d in ufs.items() if d.get(indice) is None]
        assert not faltando, (
            f"{indice} ausente em {faltando}. As três fontes foram lidas para "
            "o país inteiro; ausência aqui significa que um passo não rodou.")
        fora = [(u, d[indice]) for u, d in ufs.items()
                if not 0 <= d[indice] <= 1]
        assert not fora, f"{indice} fora de 0..1: {fora}"


def test_subgrupos_da_raps_nao_substituem_o_total():
    """
    O total conta estabelecimentos distintos, então a soma dos três subgrupos
    é MAIOR ou igual — nunca menor.

    Se a soma ficasse menor que o total, haveria classificação do serviço 115
    fora dos três subgrupos, e o extrator estaria contando algo que não
    declarou onde encaixa.
    """
    ufs = _ler("nacional.json")["ufs"]
    for sigla, d in ufs.items():
        total = d.get("municipios_com_raps")
        if total is None:
            continue
        partes = [d.get(f"municipios_com_raps_{g}") or 0 for g in SUBGRUPOS_RAPS]
        assert sum(partes) >= total, (
            f"{sigla}: soma dos subgrupos ({sum(partes)}) menor que o total "
            f"({total}) — há classificação do 115 sem subgrupo declarado")
        for grupo, parte in zip(SUBGRUPOS_RAPS, partes):
            assert parte <= total, (
                f"{sigla}: subgrupo {grupo} ({parte}) maior que o total ({total})")


def test_cobertura_socioassistencial():
    ufs = _ler("nacional.json")["ufs"]
    assert _soma(ufs, "cras_total") == CRAS_TOTAL
    assert _soma(ufs, "creas_total") == CREAS_TOTAL
    assert _soma(ufs, "municipios_com_cras") == MUNICIPIOS_COM_CRAS
    assert _soma(ufs, "municipios_com_creas") == MUNICIPIOS_COM_CREAS


def test_icap_esta_quase_saturado_e_isso_esta_dito():
    """
    Registra a saturação do ICAP, que muda como ele deve ser lido.

    5.523 dos 5.571 municípios têm psicólogo vinculado ao SUS. O índice
    continua legítimo — 87,5% no Amapá contra 100% em São Paulo é diferença
    real, e um em cada oito municípios amapaenses sem nenhum psicólogo é um
    fato —, mas ele separa pouco, e quem o ler como se fosse o retrato da rede
    vai concluir que o país inteiro está igualmente atendido. A medida que
    separa é a densidade.

    Se um dia a cobertura cair a ponto de a amplitude alargar, a ressalva deixa
    de fazer sentido e este teste é onde isso aparece.
    """
    ufs = _ler("nacional.json")["ufs"]
    valores = [d["ICAP"] for d in ufs.values() if d.get("ICAP") is not None]
    assert len(valores) == 27
    assert min(valores) > 0.8, (
        f"ICAP mínimo em {min(valores):.3f}. Abaixo de 0,8 a amplitude deixa "
        "de ser estreita e as ressalvas de saturação precisam ser revistas.")
    # A densidade, que é a medida discriminante, tem de existir em toda UF.
    densidades = [d.get("psicologos_por_100k") for d in ufs.values()]
    assert all(v is not None for v in densidades), (
        "psicologos_por_100k ausente em alguma UF — é ela que separa os "
        "estados onde o ICAP satura")
    assert max(densidades) / min(densidades) > 1.5, (
        "a densidade deveria variar bem mais que o ICAP; se não varia, o "
        "argumento de que ela é a medida discriminante caiu")


def test_cras_e_quase_universal_e_por_isso_nao_e_indice():
    """
    Documenta a razão de o CRAS não ter índice de cobertura.

    Se um dia a cobertura cair a ponto de haver variação real entre estados, o
    argumento deixa de valer e o indicador merece ser reconsiderado — e este
    teste é o lugar onde isso aparece.
    """
    ufs = _ler("nacional.json")["ufs"]
    fracao = _soma(ufs, "municipios_com_cras") / _soma(ufs, "municipios_total")
    assert fracao > 0.98, (
        f"cobertura de CRAS em {fracao:.1%}. Abaixo de 98% a justificativa "
        "para publicá-lo só como contagem e densidade — e não como índice — "
        "precisa ser revista.")
    from_catalogo = _ler("nacional.json")["ufs"]
    assert all("ICAS" in d for d in from_catalogo.values())


# ------------------------------------------------------- princípio inegociável

def test_ausencia_nunca_e_zero():
    """
    O par de `test_zero_de_ead_e_medida_nao_ausencia`, na direção oposta.

    Regra: um indicador que depende de insumo faltante não pode ter valor
    numérico. `None` chega à tela como "sem dados"; `0` chega como afirmação.
    """
    ufs = _ler("nacional.json")["ufs"]
    problemas = []
    for sigla, d in ufs.items():
        if not d.get("tem_avaliacao"):
            for campo in ("CPC", "CPC_cont", "IDD", "IAF"):
                if d.get(campo) is not None:
                    problemas.append(
                        f"{sigla}.{campo} = {d[campo]} sem curso avaliado")
        if not d.get("tem_oferta_presencial"):
            for campo in ("ICT", "E", "IAF", "HHI", "HHI_mantenedora"):
                if d.get(campo) is not None:
                    problemas.append(
                        f"{sigla}.{campo} = {d[campo]} sem oferta presencial")
    assert not problemas, ("valores numéricos onde deveria haver ausência:\n  - "
                          + "\n  - ".join(problemas))


def test_iaf_so_existe_com_os_tres_componentes():
    ufs = _ler("nacional.json")["ufs"]
    problemas = []
    for sigla, d in ufs.items():
        tem_tudo = (d.get("CPC") is not None
                    and d.get("vagas_avaliadas") is not None
                    and d.get("ICT") is not None)
        if d.get("IAF") is not None and not tem_tudo:
            problemas.append(f"{sigla}: IAF={d['IAF']} sem os três componentes")
        if d.get("IAF") is None and tem_tudo:
            problemas.append(f"{sigla}: componentes completos mas IAF nulo")
    assert not problemas, "\n  - ".join(problemas)


def test_percentuais_dentro_da_faixa():
    ufs = _ler("nacional.json")["ufs"]
    problemas = []
    for sigla, d in ufs.items():
        for campo, valor in d.items():
            if campo.startswith("pct_") and valor is not None:
                if not 0 <= valor <= 100:
                    problemas.append(f"{sigla}.{campo} = {valor}")
    assert not problemas, "percentuais fora de 0..100:\n  - " + "\n  - ".join(problemas)


# ---------------------------------------------------------------- proveniência

def test_proveniencia_vem_do_arquivo():
    """
    O ano do Censo tem de vir do arquivo lido, não do calendário.

    Derivar `ano - 1` da data de hoje rotula o Censo 2024 como 2025 durante todo
    o ano seguinte, e o erro só aparece muito depois, num gráfico de série.
    """
    meta = _ler("nacional.json")["metadados"]
    assert meta["ano_censo"] == CENSO
    prov = meta["proveniencia"]["fontes"]["censo"]
    assert prov.get("ano_censo") == CENSO
    assert prov.get("md5_publicado"), "sem md5 publicado pelo INEP na proveniência"
    assert str(CENSO) in prov.get("membro_cursos", ""), (
        "o membro lido não confere com o ano declarado")
    assert prov.get("rotulo_cine") == "Psicologia", (
        f"rótulo CINE {prov.get('rotulo_cine')!r} — o match é EXATO, e "
        "'Psicopedagogia' tem 6.083 registros contra 1.372 de 'Psicologia'")
    assert prov.get("linhas_curso") == REGISTROS_CENSO


def test_todas_as_fontes_declaram_presenca():
    fontes = _ler("_proveniencia.json")["fontes"]
    for nome in ("censo", "cpc", "cnes", "cadsuas",
                 "ibge_municipios", "ibge_populacao"):
        assert nome in fontes, f"fonte {nome} não declarada na proveniência"
        assert "presente" in fontes[nome], (
            f"fonte {nome} sem o campo `presente` — ficaria de fora de "
            "qualquer varredura que pergunte quais fontes faltaram")
    assert fontes["cnes"].get("competencia") == COMPETENCIA_CNES
    assert fontes["cadsuas"].get("anomes") == ANOMES_SUAS


def test_limitacoes_declaradas():
    """O que não foi medido precisa estar escrito, não subentendido."""
    prov = _ler("_proveniencia.json")
    texto = " ".join(prov["limitacoes_conhecidas"]).lower()
    for termo, motivo in [
        ("ead", "a quase ausência da EaD"),
        ("suas", "a origem da cobertura socioassistencial"),
        ("cras", "a razão de o CRAS não virar índice"),
        ("ocupação", "a impossibilidade de contar psicólogos no SUAS"),
        ("115", "os três recortes da rede psicossocial"),
    ]:
        assert termo in texto, f"{motivo} não está declarada nas limitações"


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
    print(f"\n{len(testes) - falhas}/{len(testes)} testes de integridade passaram.")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
