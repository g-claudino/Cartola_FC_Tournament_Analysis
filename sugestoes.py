"""
Sugestões de escalação a partir de dados públicos do Cartola (sem token).

Fontes: atletas/mercado (preço, média, jogos, status), partidas (mando e
posição na tabela de cada clube) e mercado/status.

Nota de cada jogador (só "Provável"):
  média ajustada = (média × jogos + média da posição × 3) / (jogos + 3)
  × mando (casa 1,08 · fora 0,95)
  × adversário (0,90 contra o 1º da tabela ... 1,10 contra o 20º)

A nota é uma estimativa simples, não uma previsão: serve para comparar opções.
"""
import html
import itertools
import json
from pathlib import Path

POS = {1: "GOL", 2: "LAT", 3: "ZAG", 4: "MEI", 5: "ATA", 6: "TEC"}
ORDEM_POS = [1, 2, 3, 4, 5, 6]
FORMACOES = {
    "3-4-3": {1: 1, 2: 0, 3: 3, 4: 4, 5: 3, 6: 1},
    "3-5-2": {1: 1, 2: 0, 3: 3, 4: 5, 5: 2, 6: 1},
    "4-3-3": {1: 1, 2: 2, 3: 2, 4: 3, 5: 3, 6: 1},
    "4-4-2": {1: 1, 2: 2, 3: 2, 4: 4, 5: 2, 6: 1},
    "4-5-1": {1: 1, 2: 2, 3: 2, 4: 5, 5: 1, 6: 1},
    "5-3-2": {1: 1, 2: 2, 3: 3, 4: 3, 5: 2, 6: 1},
    "5-4-1": {1: 1, 2: 2, 3: 3, 4: 4, 5: 1, 6: 1},
}
PROVAVEL = 7
CANDIDATOS_POR_POSICAO = 18


# ---------------------------------------------------------------- notas

def jogos_da_rodada(partidas):
    jogo = {}
    for p in partidas.get("partidas", []):
        if p.get("valida") is False:
            continue
        casa, fora = p["clube_casa_id"], p["clube_visitante_id"]
        jogo[casa] = dict(casa=True, adv=fora, adv_pos=p.get("clube_visitante_posicao"))
        jogo[fora] = dict(casa=False, adv=casa, adv_pos=p.get("clube_casa_posicao"))
    return jogo


def minimo_valorizar(a):
    """Pontuação mínima para o preço subir no próximo jogo. Usa o valor oficial do
    Cartola quando a API o traz; senão, a fórmula de valorizacao.py (pontos da última
    rodada como pontuação anterior)."""
    oficial = a.get("minimo_para_valorizar")
    if isinstance(oficial, (int, float)):
        return round(float(oficial), 2)
    try:
        import valorizacao
        return round(valorizacao.minimo_para_valorizar(float(a.get("preco_num") or 0),
                                                       float(a.get("pontos_num") or 0),
                                                       int(a.get("jogos_num") or 0) + 1), 2)
    except Exception:
        return None


def avaliar(mercado, partidas):
    clubes = {int(k): v for k, v in (mercado.get("clubes") or partidas.get("clubes") or {}).items()}
    jogo = jogos_da_rodada(partidas)
    atletas = mercado.get("atletas", [])

    medias_pos = {}
    for pos in POS:
        vals = [a["media_num"] for a in atletas if a.get("posicao_id") == pos and (a.get("jogos_num") or 0) > 0]
        medias_pos[pos] = sum(vals) / len(vals) if vals else 0.0

    sigla = lambda cid: (clubes.get(cid) or {}).get("abreviacao") or str(cid)  # noqa: E731
    jogadores = []
    for a in atletas:
        cid, pos, j = a.get("clube_id"), a.get("posicao_id"), a.get("jogos_num") or 0
        if a.get("status_id") != PROVAVEL or cid not in jogo or pos not in POS or j == 0:
            continue
        g = jogo[cid]
        base = (a["media_num"] * j + medias_pos[pos] * 3) / (j + 3)
        mando = 1.08 if g["casa"] else 0.95
        adv = 0.9 + 0.2 * (g["adv_pos"] - 1) / 19 if g.get("adv_pos") else 1.0
        jogadores.append(dict(
            id=a["atleta_id"], nome=a.get("apelido") or a.get("nome"), pos=pos,
            clube=sigla(cid), adv=sigla(g["adv"]), casa=g["casa"], adv_pos=g.get("adv_pos"),
            preco=round(float(a.get("preco_num") or 0), 2), media=round(float(a["media_num"]), 2),
            jogos=j, nota=round(base * mando * adv, 2), minimo=minimo_valorizar(a)))
    return jogadores


# ---------------------------------------------------------------- melhor time por orçamento

def fronteira(itens):
    """Mantém só combinações (custo, nota, ids) que nenhuma outra mais barata supera."""
    itens = sorted(itens, key=lambda x: (x[0], -x[1]))
    out, melhor = [], float("-inf")
    for c, s, ids in itens:
        if s > melhor + 1e-9:
            out.append((c, s, ids))
            melhor = s
    return out


def candidatos(jogadores, pos):
    lista = [j for j in jogadores if j["pos"] == pos]
    por_nota = sorted(lista, key=lambda j: -j["nota"])[:CANDIDATOS_POR_POSICAO // 2]
    por_custo = sorted(lista, key=lambda j: -j["nota"] / max(j["preco"], 0.5))[:CANDIDATOS_POR_POSICAO // 2]
    unicos = {j["id"]: j for j in por_nota + por_custo}
    for c, s, ids in fronteira([(j["preco"], j["nota"], (j["id"],)) for j in lista]):
        unicos.setdefault(ids[0], next(j for j in lista if j["id"] == ids[0]))
    return sorted(unicos.values(), key=lambda j: -j["nota"])[:CANDIDATOS_POR_POSICAO + 6]


def melhores_times(jogadores, orcamentos):
    por_id = {j["id"]: j for j in jogadores}
    cand = {pos: candidatos(jogadores, pos) for pos in POS}
    teto = max(orcamentos)
    resultado = {b: None for b in orcamentos}
    for nome_f, f in FORMACOES.items():
        total = [(0.0, 0.0, ())]
        for pos in ORDEM_POS:
            k = f[pos]
            if k == 0:
                continue
            if len(cand[pos]) < k:
                total = []
                break
            combos = fronteira([(sum(j["preco"] for j in c), sum(j["nota"] for j in c), tuple(j["id"] for j in c))
                                for c in itertools.combinations(cand[pos], k)])
            total = fronteira([(c1 + c2, s1 + s2, i1 + i2) for c1, s1, i1 in total for c2, s2, i2 in combos
                               if c1 + c2 <= teto + 1e-9])
        for b in orcamentos:
            ok = [t for t in total if t[0] <= b + 1e-9]
            if not ok:
                continue
            custo, nota, ids = max(ok, key=lambda t: t[1])
            if resultado[b] is None or nota > resultado[b]["nota"]:
                time = sorted((por_id[i] for i in ids), key=lambda j: (ORDEM_POS.index(j["pos"]), -j["nota"]))
                capitao = max((j for j in time if j["pos"] != 6), key=lambda j: j["nota"])
                resultado[b] = dict(formacao=nome_f, custo=round(custo, 2), nota=round(nota, 2),
                                    capitao=capitao["id"], time=time)
    return resultado


# ---------------------------------------------------------------- página

def montar(mercado, partidas, status, orcamentos):
    jogadores = avaliar(mercado, partidas)
    top = {POS[p]: sorted((j for j in jogadores if j["pos"] == p), key=lambda j: -j["nota"])[:5] for p in POS}
    baratos = sorted((j for j in jogadores if j["preco"] <= 5 and j["pos"] != 6), key=lambda j: -j["nota"])[:8]
    times = melhores_times(jogadores, orcamentos)
    return dict(rodada=status.get("rodada_atual"), mercado_aberto=status.get("status_mercado") == 1,
                jogadores_avaliados=len(jogadores), times={str(b): t for b, t in times.items()},
                top_por_posicao=top, baratos=baratos)


def _linha(j, capitao=None):
    mando = "em casa" if j["casa"] else "fora"
    pos_adv = f" ({j['adv_pos']}º)" if j.get("adv_pos") else ""
    c = " <span class='tag'>C</span>" if capitao == j["id"] else ""
    return (f"<tr><td>{POS[j['pos']]}</td><td class='n'>{html.escape(j['nome'])}{c}"
            f"<small>{html.escape(j['clube'])} · vs {html.escape(j['adv'])}{pos_adv} · {mando}</small></td>"
            f"<td>{j['preco']:.2f}</td><td>{j['media']:.2f}</td><td>{_fmt(j.get('minimo'))}</td><td><b>{j['nota']:.2f}</b></td></tr>")


def _fmt(v):
    return "–" if v is None else f"{v:.1f}"


CABECALHO = ("<div class='scroll'><table><tr><th>Pos</th><th style='text-align:left'>Jogador</th>"
             "<th>C$</th><th>Média</th><th>Mín.</th><th>Nota</th></tr>")


def gerar_html(dados, css, titulo, agora, nav=""):
    estado = (f"Mercado aberto · rodada {dados['rodada']}" if dados["mercado_aberto"]
              else f"Mercado fechado · rodada {dados['rodada']}")
    out = [f"<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
           f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>Sugestões – {html.escape(titulo)}</title>"
           f"<style>{css} details{{background:var(--card);border-radius:10px;margin:10px 0;padding:4px 12px}}"
           f"summary{{cursor:pointer;padding:10px 0;font-weight:600}} nav a{{color:var(--acc);margin-right:14px}}</style></head><body>"
           f"<header><h1>Sugestões da rodada</h1><div class='sub'>{estado} · atualizado em {agora} (Brasília)</div>"
           f"{nav}</header><main>"]
    out.append("<h2>Time sugerido por orçamento</h2>")
    for b, t in dados["times"].items():
        if not t:
            out.append(f"<details><summary>C$ {b}: sem time possível</summary></details>")
            continue
        aberto = " open" if b == list(dados["times"])[0] else ""
        out.append(f"<details{aberto}><summary>Até C$ {b} · {t['formacao']} · custa C$ {t['custo']:.2f} · nota {t['nota']:.1f}</summary>")
        out.append(CABECALHO + "".join(_linha(j, t["capitao"]) for j in t["time"]) + "</table></div></details>")
    out.append("<h2>Melhores por posição</h2>")
    for pos, lista in dados["top_por_posicao"].items():
        out.append(f"<h3>{pos}</h3>" + CABECALHO + "".join(_linha(j) for j in lista) + "</table></div>")
    out.append("<h2>Custo-benefício (até C$ 5)</h2>" + CABECALHO + "".join(_linha(j) for j in dados["baratos"]) + "</table></div>")
    out.append(f"<p class='sub'>Só jogadores com status Provável ({dados['jogadores_avaliados']} avaliados). "
               "Nota = média ajustada pelo número de jogos × mando (casa 1,08, fora 0,95) × força do adversário "
               "(0,90 contra o 1º da tabela até 1,10 contra o 20º). É uma estimativa para comparar opções, não uma previsão. "
               "C = capitão sugerido. Mín. = pontuação mínima para o jogador valorizar no próximo jogo "
               "(fórmula estimada a partir do histórico de preços; erro típico de C$ 0,05).</p></main></body></html>")
    return "".join(out)


def gerar(get_publico, saida, css, titulo, agora, orcamentos, nav=""):
    status = get_publico("mercado/status")
    dados = montar(get_publico("atletas/mercado"), get_publico("partidas"), status, orcamentos)
    saida = Path(saida)
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "sugestoes.html").write_text(gerar_html(dados, css, titulo, agora, nav), encoding="utf-8")
    (saida / "sugestoes.json").write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dados
