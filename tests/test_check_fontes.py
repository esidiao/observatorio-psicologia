"""
tests/test_check_fontes.py
Testa o verificador de frescor com a rede SIMULADA.

O que este teste protege é uma regressão específica, que no observatório de
Farmácia voltou duas vezes: tratar falha de rede como "sem novidade". Quando
isso acontece, o alerta semanal nunca dispara — e o silêncio é indistinguível
de "está tudo em dia". É a pior classe de defeito de monitoramento, porque o
sintoma é a ausência de sintoma.

Por isso os casos abaixo insistem no contrato de TRÊS estados:
    True  -> publicada
    False -> confirmadamente ausente
    None  -> indeterminado

Nenhuma rede real é usada. Roda como script ou sob pytest.
"""
import sys
import urllib.error
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "etl"))

import rede  # noqa: E402
import pipeline  # noqa: E402


class _Resposta:
    def __init__(self, status, headers=None):
        self.status = status
        self.headers = headers or {}

    def close(self):
        pass


def _com_abrir(func):
    """Troca rede._abrir por `func` durante o teste."""
    def decorador(teste):
        def envolvido():
            original = rede._abrir
            rede._abrir = func
            try:
                return teste()
            finally:
                rede._abrir = original
        envolvido.__name__ = teste.__name__
        return envolvido
    return decorador


# --------------------------------------------------------------------------- #
# sondar
# --------------------------------------------------------------------------- #

@_com_abrir(lambda url, headers=None, timeout=None: _Resposta(206))
def test_publicada_devolve_true():
    existe, detalhe = rede.sondar("https://exemplo/arquivo.zip", tentativas=1)
    assert existe is True, f"esperado True, veio {existe!r}"
    assert detalhe == "206"


def _erro_404(url, headers=None, timeout=None):
    raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)


@_com_abrir(_erro_404)
def test_ausente_devolve_false():
    existe, detalhe = rede.sondar("https://exemplo/arquivo.zip", tentativas=1)
    assert existe is False, f"esperado False, veio {existe!r}"
    assert detalhe == "404"


def _erro_rede(url, headers=None, timeout=None):
    raise OSError("conexão recusada")


@_com_abrir(_erro_rede)
def test_falha_de_rede_devolve_none_nunca_false():
    """
    A regressão central. Falha de rede NÃO é ausência.

    Se esta função devolver False, o verificador semanal conclui que a edição
    nova não existe e nunca alerta. Se devolver True, alerta toda semana sem
    motivo. `None` é a única resposta honesta: não foi possível saber.
    """
    existe, detalhe = rede.sondar("https://exemplo/arquivo.zip", tentativas=2, espera=0)
    assert existe is not False, (
        "falha de rede devolveu False — o alerta de fonte nova ficaria mudo")
    assert existe is None, f"esperado None, veio {existe!r}"
    assert detalhe, "o motivo do indeterminado precisa ser reportado"


@_com_abrir(lambda url, headers=None, timeout=None: _Resposta(503))
def test_erro_de_servidor_e_indeterminado():
    existe, _ = rede.sondar("https://exemplo/arquivo.zip", tentativas=1)
    assert existe is None, f"503 deveria ser indeterminado, veio {existe!r}"


def test_sondar_nunca_devolve_booleano_puro():
    """
    Contrato estrutural: o retorno é sempre uma dupla (estado, detalhe).

    É o que impede alguém de escrever `if sondar(url):` e tratar None como
    False sem perceber.
    """
    import inspect
    fonte = inspect.getsource(rede.sondar)
    assert "return None" in fonte or "None, ultimo" in fonte, (
        "sondar precisa de um caminho explícito para o indeterminado")


# --------------------------------------------------------------------------- #
# série anual
# --------------------------------------------------------------------------- #

def test_serie_anual_separa_novidade_de_indeterminado():
    respostas = {2025: (True, "206"), 2026: (None, "Timeout")}
    original = pipeline.sondar
    pipeline.sondar = lambda url, **kw: respostas[int(url.split("=")[-1])]
    try:
        novidades, indeterminados = pipeline._serie_anual(
            "Teste", "https://exemplo/x?ano={ano}", 2024, 2026)
    finally:
        pipeline.sondar = original
    assert novidades == ["Teste 2025"], novidades
    assert len(indeterminados) == 1, indeterminados
    assert "2026" in indeterminados[0]


def test_serie_anual_sem_ano_atual_nao_afirma_nada():
    """
    Sem saber o ano corrente, o verificador não pode dizer "nada mudou".

    Devolver listas vazias aqui seria afirmar que está tudo em dia com base em
    nenhuma informação — o mesmo erro de tratar indeterminado como ausente,
    numa roupagem diferente.
    """
    novidades, indeterminados = pipeline._serie_anual(
        "Teste", "https://exemplo/x?ano={ano}", None, 2026)
    assert novidades == []
    assert indeterminados, (
        "ano corrente desconhecido tem de virar indeterminado, não silêncio")


# --------------------------------------------------------------------------- #
# fontes sem sondagem
# --------------------------------------------------------------------------- #

def test_fontes_sem_sondagem_tem_motivo_concreto():
    """
    Uma fonte que não dá para verificar precisa dizer POR QUÊ.

    "Não verificável" sem motivo vira desculpa permanente; com motivo, vira um
    item que alguém pode revisitar quando a fonte mudar.
    """
    assert pipeline.FONTES_SEM_SONDAGEM, "nenhuma fonte declarada como não sondável"
    for nome, motivo in pipeline.FONTES_SEM_SONDAGEM.items():
        assert len(motivo) > 40, f"{nome}: motivo curto demais para ser útil"


# --------------------------------------------------------------------------- #
# série anual com várias grafias — o caso do CPC
# --------------------------------------------------------------------------- #

def test_multi_acha_a_edicao_na_segunda_grafia():
    """
    O CPC 2022 só existe em minúscula: `cpc_2022.xlsx`. Sondar apenas
    `CPC_2022.xlsx` devolve 404 e o verificador concluiria que o ciclo não foi
    publicado — que foi como esse ciclo quase ficou de fora do observatório.
    """
    respostas = {
        "https://x/CPC_2025.xlsx": (False, "404"),
        "https://x/cpc_2025.xlsx": (True, "206"),
    }
    original = pipeline.sondar
    pipeline.sondar = lambda url, **kw: respostas[url]
    try:
        novidades, indeterminados = pipeline._serie_anual_multi(
            "CPC", ["https://x/CPC_{ano}.xlsx", "https://x/cpc_{ano}.xlsx"],
            2024, 2025)
    finally:
        pipeline.sondar = original
    assert novidades == ["CPC 2025"], novidades
    assert not indeterminados


def test_multi_so_declara_ausente_quando_TODAS_as_grafias_dao_404():
    respostas = {
        "https://x/CPC_2025.xlsx": (False, "404"),
        "https://x/cpc_2025.xlsx": (False, "404"),
    }
    original = pipeline.sondar
    pipeline.sondar = lambda url, **kw: respostas[url]
    try:
        novidades, indeterminados = pipeline._serie_anual_multi(
            "CPC", ["https://x/CPC_{ano}.xlsx", "https://x/cpc_{ano}.xlsx"],
            2024, 2025)
    finally:
        pipeline.sondar = original
    assert not novidades
    assert not indeterminados, (
        "duas grafias com 404 confirmado é ausência confirmada, não dúvida")


def test_multi_uma_grafia_indeterminada_contamina_o_ano():
    """
    404 numa grafia e falha de rede na outra NÃO é ausência.

    Sem este cuidado, bastaria a segunda sondagem cair para o verificador
    afirmar que a edição não existe — a mesma confusão entre indeterminado e
    ausente, um nível acima.
    """
    respostas = {
        "https://x/CPC_2025.xlsx": (False, "404"),
        "https://x/cpc_2025.xlsx": (None, "Timeout"),
    }
    original = pipeline.sondar
    pipeline.sondar = lambda url, **kw: respostas[url]
    try:
        novidades, indeterminados = pipeline._serie_anual_multi(
            "CPC", ["https://x/CPC_{ano}.xlsx", "https://x/cpc_{ano}.xlsx"],
            2024, 2025)
    finally:
        pipeline.sondar = original
    assert not novidades
    assert len(indeterminados) == 1, indeterminados
    assert "2025" in indeterminados[0]


def test_multi_sem_ano_atual_nao_afirma_nada():
    novidades, indeterminados = pipeline._serie_anual_multi(
        "CPC", ["https://x/CPC_{ano}.xlsx"], None, 2026)
    assert novidades == []
    assert indeterminados



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
    print(f"\n{len(testes) - falhas}/{len(testes)} testes do verificador passaram.")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
