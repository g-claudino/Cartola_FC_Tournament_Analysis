"""
Modelo da variação de preço do Cartola, obtido por engenharia reversa dos dados
públicos rodada a rodada de 2024–2026 (repositório henriquepgomide/caRtola).

O preço só muda quando o jogador entra em campo. Com n = jogos do jogador na
temporada (contando o atual), p = pontos no jogo, p1 = pontos no jogo anterior
dele e P = preço antes da rodada:

  n >= 6:  variação = K·(p − p1) + (A·p + B·p1 − C·P + D) / n
  n <= 5:  variação = c + a·p + b·p1 + d·P   (coeficientes próprios de cada n)

Em palavras: o preço sobe se o jogador supera a própria pontuação anterior
(termo K) e se a pontuação está acima do que o preço "pede" (termo / n, que pesa
menos à medida que a temporada avança).

Precisão na temporada 2026, ajustando só com 2024–2025: ver avaliar() ou o README.
O que sobra (~C$ 0,04 típico) não é explicado por nenhum dado público disponível.
"""

# Ajuste em 2024–2026 (python valorizacao.py ajustar  para refazer)
COEF = {
    "geral": {"K": 0.1275, "A": 0.5103, "B": 0.1185, "C": 0.3400, "D": -0.0296},
    # n: (c, a·p, d·P, b·p1)
    "inicio": {
        1: (0.1395, 0.3452, -0.1671, 0.0),
        2: (0.0566, 0.2722, -0.1331, 0.0044),
        3: (0.0173, 0.2435, -0.1136, -0.0446),
        4: (-0.0426, 0.2369, -0.0948, -0.0669),
        5: (-0.0364, 0.2286, -0.0902, -0.0833),
    },
}


def variacao(preco, pontos, pontos_anterior, jogos, coef=COEF):
    """Variação de preço prevista após um jogo. `jogos` inclui o jogo atual."""
    p1 = pontos_anterior or 0.0
    if jogos <= 5:
        c, a, d, b = coef["inicio"][max(1, int(jogos))]
        return c + a * pontos + b * p1 + d * preco
    g = coef["geral"]
    return g["K"] * (pontos - p1) + (g["A"] * pontos + g["B"] * p1 - g["C"] * preco + g["D"]) / jogos


def minimo_para_valorizar(preco, pontos_anterior, jogos, coef=COEF):
    """Pontuação a partir da qual o preço sobe no próximo jogo (jogos = jogos já feitos + 1)."""
    p1 = pontos_anterior or 0.0
    if jogos <= 5:
        c, a, d, b = coef["inicio"][max(1, int(jogos))]
        return -(c + b * p1 + d * preco) / a
    g = coef["geral"]
    n = jogos
    return (g["K"] * n * p1 - g["B"] * p1 + g["C"] * preco - g["D"]) / (g["K"] * n + g["A"])


# ---------------------------------------------------------------- ajuste e avaliação (precisa dos CSVs do caRtola)

def _painel(pasta, anos):
    import glob
    import re
    import pandas as pd
    fr = []
    for ano in anos:
        for f in glob.glob(f"{pasta}/{ano}/rodada-*.csv"):
            d = pd.read_csv(f, low_memory=False)
            d.columns = [c.replace("atletas.", "") for c in d.columns]
            d["ano"], d["rodada"] = ano, int(re.search(r"rodada-(\d+)", f).group(1))
            fr.append(d)
    df = pd.concat(fr, ignore_index=True)
    df["preco_antes"] = (df.preco_num - df.variacao_num).round(2)
    j = df[df.entrou_em_campo == True].sort_values(["ano", "atleta_id", "rodada"]).copy()  # noqa: E712
    g = j.groupby(["ano", "atleta_id"])
    j["n"] = g.cumcount() + 1
    j["p1"] = g.pontos_num.shift(1).fillna(0.0)
    return j


def ajustar(j):
    import numpy as np
    from scipy.optimize import least_squares
    coef = {"inicio": {}}
    for n in range(1, 6):
        s = j[j.n == n]
        X = np.column_stack([np.ones(len(s)), s.pontos_num, s.preco_antes, s.p1])
        b, *_ = np.linalg.lstsq(X, s.variacao_num, rcond=None)
        coef["inicio"][n] = tuple(round(float(x), 4) for x in b)
    s = j[j.n >= 6]
    def res(t):
        return t[0] * (s.pontos_num - s.p1) + (t[1] * s.pontos_num + t[2] * s.p1 - t[3] * s.preco_antes + t[4]) / s.n - s.variacao_num
    t = least_squares(res, [0.13, 0.5, 0.13, 0.35, 0.0]).x
    coef["geral"] = dict(zip("KABCD", (round(float(x), 4) for x in t)))
    return coef


def avaliar(j, coef):
    import numpy as np
    prev = np.array([variacao(r.preco_antes, r.pontos_num, r.p1, r.n, coef) for r in j.itertuples()])
    erro = np.abs(prev - j.variacao_num.values)
    acerto_sinal = np.mean(np.sign(np.round(prev, 2)) == np.sign(j.variacao_num.values))
    return dict(jogos=len(j), erro_mediano=round(float(np.median(erro)), 3), erro_medio=round(float(erro.mean()), 3),
                ate_005=round(float(np.mean(erro <= 0.05)), 3), ate_010=round(float(np.mean(erro <= 0.10)), 3),
                sinal_certo=round(float(acerto_sinal), 3))


if __name__ == "__main__":
    import sys
    pasta = sys.argv[2] if len(sys.argv) > 2 else "caRtola/data/01_raw"
    j = _painel(pasta, [2024, 2025, 2026])
    treino = ajustar(j[j.ano.isin([2024, 2025])])
    print("Ajuste 2024–2025:", treino)
    print("Teste em 2026:", avaliar(j[j.ano == 2026], treino))
    if len(sys.argv) > 1 and sys.argv[1] == "ajustar":
        print("Ajuste 2024–2026:", ajustar(j))
