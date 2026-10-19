"""
Página de cada time (docs/time-<id>.html) com a escalação de cada rodada da fase:
titulares, capitão, pontos, reservas que entraram e banco.

O Cartola só mostra a escalação depois que o mercado fecha, então a rodada que
ainda está sendo montada não aparece.
"""
import html
from pathlib import Path

POS = {1: "GOL", 2: "LAT", 3: "ZAG", 4: "MEI", 5: "ATA", 6: "TEC"}
ORDEM = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5}


def link(t, texto=None):
    """Nome do time com link para a página dele."""
    rotulo = html.escape(texto if texto is not None else t["nome"])
    if not t.get("time_id"):
        return rotulo
    return f"<a class='tl' href='time-{t['time_id']}.html'>{rotulo}</a>"


CSS_EXTRA = """
a.tl{color:inherit;text-decoration:none;border-bottom:1px dotted var(--sub)}
details.rd{background:var(--card);border-radius:10px;margin:10px 0;padding:2px 12px}
details.rd summary{cursor:pointer;padding:12px 0;font-weight:600;display:flex;justify-content:space-between}
.esc td{padding:7px 4px}.esc td.p{color:var(--sub);font-size:12px;width:34px}
.esc small{display:block;color:var(--sub)}.esc .pts{text-align:right;white-space:nowrap}
.sai{text-decoration:line-through;color:var(--sub)}.ent{color:var(--win);font-size:13px}
.aj{color:var(--sub);font-style:italic}
"""


def _clube(clubes, cid):
    return html.escape(str(clubes.get(str(cid)) or clubes.get(cid) or ""))


def _num(v):
    return f"{v:.2f}"


def _tabela(d, clubes):
    linhas = []
    for j in sorted(d["jogadores"], key=lambda j: ORDEM.get(j["pos"], 9)):
        cap = " <span class='tag'>C</span>" if j["capitao"] else ""
        if j["entrou"]:
            e = j["entrou"]
            nome = (f"<span class='sai'>{html.escape(j['nome'])}</span>{cap}"
                    f"<small class='ent'>↳ {'reserva de luxo' if e['luxo'] else 'reserva'}: {html.escape(e['nome'])} "
                    f"({_clube(clubes, e['clube'])})</small>")
            pts = f"<b>{_num(e['pontos'])}</b>"
        else:
            nome = f"{html.escape(j['nome'])}{cap}<small>{_clube(clubes, j['clube'])}</small>"
            pts = ("<span class='aj'>a jogar</span>" if j["situacao"] == "a_jogar"
                   else f"<b>{_num(j['pontos'])}</b>" if j["situacao"] == "jogou"
                   else "<span class='aj'>não jogou</span>")
        linhas.append(f"<tr><td class='p'>{POS.get(j['pos'], '')}</td><td class='n'>{nome}</td><td class='pts'>{pts}</td></tr>")
    banco = []
    for b in sorted(d.get("banco", []), key=lambda b: ORDEM.get(b["pos"], 9)):
        marca = " · luxo" if b["luxo"] else ""
        estado = ("entrou" if b["entrou"] else "a jogar" if b["situacao"] == "a_jogar"
                  else _num(b["pontos"]) if b["situacao"] == "jogou" else "não jogou")
        banco.append(f"<tr><td class='p'>{POS.get(b['pos'], '')}</td><td class='n'>{html.escape(b['nome'])}"
                     f"<small>{_clube(clubes, b['clube'])}{marca}</small></td><td class='pts sub'>{estado}</td></tr>")
    out = "<table class='esc'>" + "".join(linhas) + "</table>"
    if banco:
        out += "<div class='sub' style='margin:10px 0 4px'>Banco</div><table class='esc'>" + "".join(banco) + "</table>"
    return out


def gerar(cfg, por_rodada, clubes, saida, css, nav, ao_vivo=None, agora=""):
    """por_rodada: {rodada: {time_id: análise de parciais.calcular_time}}."""
    saida = Path(saida)
    for chave in cfg["chaves"]:
        for t in chave["times"]:
            tid = str(t.get("time_id"))
            out = [f"<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
                   f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
                   f"<title>{html.escape(t['nome'])} – escalações</title><style>{css}{CSS_EXTRA}</style></head><body>"
                   f"<header><h1>{html.escape(t['nome'])}</h1><div class='sub'>{html.escape(t.get('cartoleiro', ''))} · "
                   f"{html.escape(chave['nome'])} · atualizado em {agora} (Brasília)</div>{nav}</header><main>"]
            rodadas = sorted((r for r in por_rodada if tid in por_rodada[r]), key=int, reverse=True)
            if not rodadas:
                out.append("<p class='sub'>Nenhuma escalação ainda. O Cartola mostra o time escolhido "
                           "quando o mercado fecha, no início de cada rodada.</p>")
            for i, r in enumerate(rodadas):
                d = por_rodada[r][tid]
                vivo = str(r) == str(ao_vivo)
                status = f" <span class='tag'>ao vivo · {d['jogaram']}/{d['escalados']}</span>" if vivo else ""
                out.append(f"<details class='rd'{' open' if i == 0 else ''}><summary><span>Rodada {r}{status}</span>"
                           f"<span>{_num(d['pontos'])}</span></summary>{_tabela(d, clubes)}</details>")
            out.append("<p class='sub'>Capitão (C) vale 1,5×. Reserva entra no lugar do titular da mesma posição que "
                       "não jogou; a reserva de luxo troca com o titular de pior pontuação da posição se pontuar mais. "
                       "O Cartola só mostra a escalação depois que o mercado fecha.</p>"
                       "<p><a class='tl' href='index.html'>← Voltar para a classificação</a></p></main></body></html>")
            (saida / f"time-{tid}.html").write_text("".join(out), encoding="utf-8")
