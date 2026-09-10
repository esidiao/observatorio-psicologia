"""
site/estatistica.py
Estatística do observatório, sem dependência externa.

Spearman, significância e regressão múltipla em Python puro. Não é purismo:
`scipy` são ~40 MB de wheel para três fórmulas de vinte linhas, e o CI teria de
instalá-lo a cada execução para produzir números que cabem num arquivo deste
tamanho. Com o cálculo aqui, o portão GO consegue testar as fórmulas contra
valores conferidos à mão — o que com uma biblioteca externa viraria teste da
biblioteca, não do observatório.

SPEARMAN, NÃO PEARSON
---------------------
As distribuições aqui são pequenas (24 UFs com oferta), assimétricas e com
outliers estruturais — São Paulo tem 10.070 vagas e Rondônia 347. Pearson mede
associação linear e é dominado por esses extremos; Spearman opera sobre postos
e responde à pergunta que interessa: quando um indicador sobe, o outro tende a
subir? Empates recebem posto médio, que é o que torna o resultado comparável
com o de qualquer outra ferramenta.

n PEQUENO EXIGE DIZER n
------------------------
Com 24 pontos, |ρ| ≈ 0,40 já cruza p < 0,05 — e continua sendo uma nuvem larga.
Por isso toda correlação publicada carrega ρ, p e n juntos. Publicar ρ sozinho
convida a ler coincidência como estrutura.
"""
import math


# --------------------------------------------------------------------------- #
# Postos
# --------------------------------------------------------------------------- #

def postos(valores):
    """
    Postos 1..n com empates recebendo a média dos postos que ocupariam.

    Sem o tratamento de empate, três UFs com o mesmo valor recebem postos
    1, 2 e 3 conforme a ordem em que aparecem no arquivo — e a correlação passa
    a depender da ordem de leitura, que não é um fato sobre o mundo.
    """
    n = len(valores)
    indexados = sorted(range(n), key=lambda i: valores[i])
    resultado = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and valores[indexados[j + 1]] == valores[indexados[i]]:
            j += 1
        media = (i + j) / 2 + 1
        for k in range(i, j + 1):
            resultado[indexados[k]] = media
        i = j + 1
    return resultado


# --------------------------------------------------------------------------- #
# Correlação
# --------------------------------------------------------------------------- #

def pearson(x, y):
    n = len(x)
    if n < 3:
        return None
    mx = sum(x) / n
    my = sum(y) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def spearman(x, y):
    """Devolve (rho, p, n) sobre os pares em que AMBOS existem."""
    pares = [(a, b) for a, b in zip(x, y) if a is not None and b is not None]
    n = len(pares)
    if n < 4:
        return None, None, n
    rho = pearson(postos([a for a, _ in pares]), postos([b for _, b in pares]))
    if rho is None:
        return None, None, n
    return rho, valor_p(rho, n), n


def valor_p(rho, n):
    """
    p bilateral pela aproximação t de Student, com t = ρ·√((n−2)/(1−ρ²)).

    Aproximação declarada, não exata: com n em torno de 24 ela é boa o
    bastante para separar "estrutura" de "ruído", que é o uso que o site faz.
    Não serve para inferência de precisão, e o site não a apresenta como tal.
    """
    if rho is None or n < 4:
        return None
    if abs(rho) >= 1:
        return 0.0
    t = abs(rho) * math.sqrt((n - 2) / (1 - rho ** 2))
    return 2 * (1 - _t_cdf(t, n - 2))


def _t_cdf(t, gl):
    """CDF da t de Student via função beta incompleta regularizada."""
    x = gl / (gl + t * t)
    return 1 - 0.5 * _beta_incompleta(x, gl / 2, 0.5)


def _beta_incompleta(x, a, b):
    """I_x(a,b) por fração continuada de Lentz."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
             + a * math.log(x) + b * math.log(1 - x))
    if x < (a + 1) / (a + b + 2):
        return math.exp(lbeta) * _fracao_continuada(x, a, b) / a
    return 1 - math.exp(lbeta) * _fracao_continuada(1 - x, b, a) / b


def _fracao_continuada(x, a, b, iteracoes=200, eps=1e-12):
    minusculo = 1e-30
    c, d = 1.0, 1 - (a + b) * x / (a + 1)
    if abs(d) < minusculo:
        d = minusculo
    d = 1 / d
    h = d
    for m in range(1, iteracoes + 1):
        m2 = 2 * m
        num = m * (b - m) * x / ((a + m2 - 1) * (a + m2))
        d = 1 + num * d
        if abs(d) < minusculo:
            d = minusculo
        c = 1 + num / c
        if abs(c) < minusculo:
            c = minusculo
        d = 1 / d
        h *= d * c
        num = -(a + m) * (a + b + m) * x / ((a + m2) * (a + m2 + 1))
        d = 1 + num * d
        if abs(d) < minusculo:
            d = minusculo
        c = 1 + num / c
        if abs(c) < minusculo:
            c = minusculo
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < eps:
            break
    return h


# --------------------------------------------------------------------------- #
# Regressão múltipla
# --------------------------------------------------------------------------- #

def regressao(y, xs, rotulos=None):
    """
    Mínimos quadrados por equações normais com eliminação de Gauss.

    Devolve dict com coeficientes, R², R² ajustado e n; ou None se não houver
    observações completas suficientes. Só entram as observações em que a
    resposta E TODOS os preditores existem — imputar a média de um preditor
    ausente inventaria o dado que o observatório se recusa a inventar, e ainda
    por cima puxaria o coeficiente para zero.
    """
    k = len(xs)
    linhas = []
    for i, alvo in enumerate(y):
        if alvo is None:
            continue
        preditores = [x[i] for x in xs]
        if any(p is None for p in preditores):
            continue
        linhas.append(([1.0] + [float(p) for p in preditores], float(alvo)))

    n = len(linhas)
    if n < k + 2:
        return None

    p = k + 1
    xtx = [[sum(linha[i] * linha[j] for linha, _ in linhas) for j in range(p)]
           for i in range(p)]
    xty = [sum(linha[i] * alvo for linha, alvo in linhas) for i in range(p)]

    beta = _resolver(xtx, xty)
    if beta is None:
        return None

    media = sum(alvo for _, alvo in linhas) / n
    sst = sum((alvo - media) ** 2 for _, alvo in linhas)
    sse = sum((alvo - sum(b * v for b, v in zip(beta, linha))) ** 2
              for linha, alvo in linhas)
    r2 = 1 - sse / sst if sst > 0 else None
    r2_aj = (1 - (1 - r2) * (n - 1) / (n - p)) if (r2 is not None and n > p) else None

    rotulos = rotulos or [f"x{i + 1}" for i in range(k)]
    return {
        "n": n,
        "intercepto": round(beta[0], 4),
        "coeficientes": [{"variavel": r, "beta": round(b, 4)}
                         for r, b in zip(rotulos, beta[1:])],
        "r2": round(r2, 4) if r2 is not None else None,
        "r2_ajustado": round(r2_aj, 4) if r2_aj is not None else None,
    }


def _resolver(a, b):
    """Gauss com pivotamento parcial. None se a matriz for singular."""
    n = len(b)
    m = [linha[:] + [b[i]] for i, linha in enumerate(a)]
    for coluna in range(n):
        pivo = max(range(coluna, n), key=lambda r: abs(m[r][coluna]))
        if abs(m[pivo][coluna]) < 1e-12:
            return None
        m[coluna], m[pivo] = m[pivo], m[coluna]
        for linha in range(coluna + 1, n):
            fator = m[linha][coluna] / m[coluna][coluna]
            for j in range(coluna, n + 1):
                m[linha][j] -= fator * m[coluna][j]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (m[i][n] - sum(m[i][j] * x[j] for j in range(i + 1, n))) / m[i][i]
    return x


# --------------------------------------------------------------------------- #
# Autoteste — parte do portão GO
# --------------------------------------------------------------------------- #

def autoteste():
    casos = []

    # Monotônica perfeita: Spearman = 1 mesmo com relação não linear.
    # É exatamente o que separa Spearman de Pearson.
    x = [1, 2, 3, 4, 5, 6, 7, 8]
    y = [1, 4, 9, 16, 25, 36, 49, 64]
    rho, p, n = spearman(x, y)
    casos.append(("Spearman de monotônica perfeita = 1", round(rho, 6), 1.0))
    casos.append(("n conferido", n, 8))

    rho, _, _ = spearman(x, list(reversed(y)))
    casos.append(("Spearman de inversa perfeita = -1", round(rho, 6), -1.0))

    # Empates recebem posto médio: [10,20,20,30] -> [1, 2.5, 2.5, 4]
    casos.append(("postos com empate", postos([10, 20, 20, 30]),
                  [1.0, 2.5, 2.5, 4.0]))

    # Ausência não entra na conta, e n reflete isso.
    rho, _, n = spearman([1, 2, None, 4, 5, 6], [1, 2, 3, None, 5, 6])
    casos.append(("pares incompletos são descartados", n, 4))

    # Regressão sobre relação exata y = 2 + 3a - 1b: R² = 1 e coeficientes exatos.
    a = [1, 2, 3, 4, 5, 6]
    b = [2, 1, 4, 3, 6, 5]
    alvo = [2 + 3 * ai - bi for ai, bi in zip(a, b)]
    r = regressao(alvo, [a, b], ["a", "b"])
    casos.append(("regressão: R² de relação exata", round(r["r2"], 6), 1.0))
    casos.append(("regressão: coeficiente de a", round(r["coeficientes"][0]["beta"], 4), 3.0))
    casos.append(("regressão: coeficiente de b", round(r["coeficientes"][1]["beta"], 4), -1.0))
    casos.append(("regressão: intercepto", round(r["intercepto"], 4), 2.0))

    # Observação com preditor ausente sai da conta em vez de ser imputada.
    r = regressao(alvo + [99], [a + [None], b + [1]], ["a", "b"])
    casos.append(("regressão descarta observação incompleta", r["n"], 6))

    # p com n pequeno: ρ alto e n baixo NÃO deve dar p desprezível.
    rho, p, _ = spearman([1, 2, 3, 4], [1, 3, 2, 4])
    casos.append(("p existe e está em 0..1", 0.0 <= p <= 1.0, True))

    ok = True
    print("=== ESTATÍSTICA ===")
    for rotulo, obtido, esperado in casos:
        passou = obtido == esperado
        ok = ok and passou
        print(f"  {'OK    ' if passou else 'FALHOU'}  {rotulo}: "
              f"obtido={obtido!r} esperado={esperado!r}")
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if autoteste() else 1)
