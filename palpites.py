"""
Palpites dos jogos da rodada (modelo de Poisson), só com dados públicos do Cartola.

Evolução do ResultPrevisionBigBrazilian.py: em vez de multiplicar médias brutas,
cada time recebe uma força de ataque e de defesa relativa à média da liga,
separada em casa e fora:

  gols esperados do mandante  = média de gols do mandante na liga × ataque_casa(M) × defesa_fora(V)
  gols esperados do visitante = média de gols do visitante na liga × ataque_fora(V) × defesa_casa(M)

As forças são puxadas para 1,0 quando há poucos jogos (encolhimento). Os placares
saem de `partidas/{rodada}`. Desfalques e jogos em outras competições entram só como
contexto na página: testados em 2026 (rodadas 8–30, validação deixando uma rodada de
fora), não melhoraram as probabilidades.
"""
import datetime as dt
import html
import json
import math
from pathlib import Path

MAX_GOLS = 8
ENCOLHIMENTO = 12.0     # "jogos fantasmas" na média da liga (ajustado nos jogos de 2026)
MEIA_VIDA = 1000.0      # rodadas; peso por recência não melhorou o acerto em 2026
EMPATE_EXTRA = 0.03     # Poisson independente subestima empates (25% previsto x 28% real em 2026)


# ---------------------------------------------------------------- dados

def resultados(get_publico, rodada_atual, cache_path):
    """Placares de todas as rodadas anteriores (em cache: rodadas encerradas não mudam)."""
    cache_path = Path(cache_path)
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    for r in range(1, rodada_atual):
        if str(r) in cache and all("data" in j for j in cache[str(r)]):
            continue
        try:
            d = get_publico(f"partidas/{r}")
        except Exception as e:
            print(f"  aviso: partidas/{r}: {e}")
            continue
        jogos = []
        for p in d.get("partidas", []):
            gm, gv = p.get("placar_oficial_mandante"), p.get("placar_oficial_visitante")
            if gm is None or gv is None:
                continue
            jogos.append(dict(casa=p["clube_casa_id"], fora=p["clube_visitante_id"], gm=int(gm), gv=int(gv),
                              data=p.get("partida_data")))
        if jogos:
            cache[str(r)] = jogos
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False) + "\n", encoding="utf-8")
    return {int(r): j for r, j in cache.items()}


# ---------------------------------------------------------------- modelo

def forcas(jogos_por_rodada, ate_rodada):
    """Forças de ataque/defesa em casa e fora, com peso maior para rodadas recentes."""
    soma = {}
    gm_tot = gv_tot = peso_tot = 0.0
    for r, jogos in jogos_por_rodada.items():
        if r >= ate_rodada:
            continue
        w = 0.5 ** ((ate_rodada - r) / MEIA_VIDA)
        for j in jogos:
            gm_tot += w * j["gm"]; gv_tot += w * j["gv"]; peso_tot += w
            c = soma.setdefault(j["casa"], dict(gfc=0, gsc=0, nc=0, gff=0, gsf=0, nf=0))
            f = soma.setdefault(j["fora"], dict(gfc=0, gsc=0, nc=0, gff=0, gsf=0, nf=0))
            c["gfc"] += w * j["gm"]; c["gsc"] += w * j["gv"]; c["nc"] += w
            f["gff"] += w * j["gv"]; f["gsf"] += w * j["gm"]; f["nf"] += w
    if peso_tot == 0:
        return None
    mc, mf = gm_tot / peso_tot, gv_tot / peso_tot   # gols por jogo do mandante / visitante
    k = ENCOLHIMENTO
    times = {}
    for t, s in soma.items():
        times[t] = dict(
            ataque_casa=(s["gfc"] + k * mc) / (s["nc"] + k) / mc,
            defesa_casa=(s["gsc"] + k * mf) / (s["nc"] + k) / mf,
            ataque_fora=(s["gff"] + k * mf) / (s["nf"] + k) / mf,
            defesa_fora=(s["gsf"] + k * mc) / (s["nf"] + k) / mc,
        )
    return dict(media_casa=mc, media_fora=mf, times=times)


def _pmf(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def prever(modelo, casa, fora):
    neutro = dict(ataque_casa=1, defesa_casa=1, ataque_fora=1, defesa_fora=1)
    c, f = modelo["times"].get(casa, neutro), modelo["times"].get(fora, neutro)
    lc = modelo["media_casa"] * c["ataque_casa"] * f["defesa_fora"]
    lf = modelo["media_fora"] * f["ataque_fora"] * c["defesa_casa"]
    pc = pe = pf = 0.0
    melhor = (0.0, 0, 0)
    for a in range(MAX_GOLS + 1):
        for b in range(MAX_GOLS + 1):
            p = _pmf(a, lc) * _pmf(b, lf)
            if a > b:
                pc += p
            elif a == b:
                pe += p
            else:
                pf += p
            if p > melhor[0]:
                melhor = (p, a, b)
    pe += EMPATE_EXTRA * (pc + pe + pf)
    tot = pc + pe + pf
    return dict(gols_casa=round(lc, 2), gols_fora=round(lf, 2), casa=round(pc / tot, 3), empate=round(pe / tot, 3),
                fora=round(pf / tot, 3), placar=f"{melhor[1]} x {melhor[2]}", placar_prob=round(melhor[0], 3))


def avaliar_historico(jogos_por_rodada, a_partir_de=8):
    """Prevê cada rodada passada só com as anteriores e compara com o resultado."""
    acertos = total = 0
    logloss = base_ll = 0.0
    freq = dict(casa=0, empate=0, fora=0)
    for r in sorted(jogos_por_rodada):
        if r < a_partir_de:
            for j in jogos_por_rodada[r]:
                freq["casa" if j["gm"] > j["gv"] else "empate" if j["gm"] == j["gv"] else "fora"] += 1
            continue
        m = forcas(jogos_por_rodada, r)
        nb = sum(freq.values())
        reais = []
        for j in jogos_por_rodada[r]:
            p = prever(m, j["casa"], j["fora"])
            real = "casa" if j["gm"] > j["gv"] else "empate" if j["gm"] == j["gv"] else "fora"
            palpite = max(("casa", "empate", "fora"), key=lambda x: p[x])
            acertos += palpite == real
            total += 1
            logloss -= math.log(max(p[real], 1e-9))
            base_ll -= math.log(max(freq[real] / nb, 1e-9))
            reais.append(real)
        for real in reais:  # só depois da rodada inteira: a referência não pode ver o resultado
            freq[real] += 1
    if not total:
        return None
    return dict(jogos=total, acerto=round(acertos / total, 3), logloss=round(logloss / total, 3),
                logloss_base=round(base_ll / total, 3))


# ---------------------------------------------------------------- página

def _dias(h):
    d = round(h / 24)
    return "hoje" if d == 0 else "1 dia" if d == 1 else f"{d} dias"


def contexto_jogo(fe, agenda, des, clube, nome_clube, quando):
    linhas = []
    if des and des.get(clube, {}).get("nomes"):
        linhas.append(f"{nome_clube} sem: {', '.join(des[clube]['nomes'][:5])}")
    if agenda is not None:
        c = fe.calendario(agenda, clube, quando)
        if c["antes"]:
            linhas.append(f"{nome_clube} jogou {c['antes']} {_dias(c['antes_h'])} antes")
        if c["depois"]:
            linhas.append(f"{nome_clube} joga {c['depois']} {_dias(c['depois_h'])} depois")
    return linhas


def montar(get_publico, status, cache_path, ext=None):
    rodada = status["rodada_atual"]
    hist = resultados(get_publico, rodada, cache_path)
    modelo = forcas(hist, rodada)
    atual = get_publico("partidas")
    clubes = {int(k): v for k, v in (atual.get("clubes") or {}).items()}
    nome = lambda cid: ((clubes.get(cid) or {}).get("nome_fantasia")  # noqa: E731
                        or (clubes.get(cid) or {}).get("nome") or str(cid))
    brt = dt.timezone(dt.timedelta(hours=-3))
    hoje = dt.datetime.now(brt).date().isoformat()

    fe = agenda = mapa = des = None
    try:
        import fontes_externas as fe
        if ext:
            mapa = fe.mapear_times(ext, hist)
            agenda = fe.agenda_outras(ext, mapa)
        des = fe.desfalques(get_publico("atletas/mercado").get("atletas", []), max(rodada - 1, 1))
    except Exception as e:
        print(f"  aviso: contexto indisponível ({e})")

    jogos = []
    for p in atual.get("partidas", []):
        if p.get("valida") is False:
            continue
        prev = prever(modelo, p["clube_casa_id"], p["clube_visitante_id"]) if modelo else None
        data = (p.get("partida_data") or "")[:16]
        ctx = []
        if fe and data:
            quando = dt.datetime.fromisoformat(data.replace(" ", "T")).replace(tzinfo=brt)
            for cid in (p["clube_casa_id"], p["clube_visitante_id"]):
                ctx += contexto_jogo(fe, agenda, des, cid, nome(cid), quando)
        jogos.append(dict(casa=nome(p["clube_casa_id"]), fora=nome(p["clube_visitante_id"]), data=data,
                          hoje=data[:10] == hoje, local=p.get("local"), previsao=prev, contexto=ctx))
    jogos.sort(key=lambda j: j["data"])

    outros = []
    if fe and ext and mapa is not None:
        for j in fe.jogos_do_dia(ext, mapa, hoje):
            j["previsao"] = (prever(modelo, j["casa_id"], j["fora_id"])
                             if modelo and j["casa_id"] and j["fora_id"] else None)
            outros.append(j)
    return dict(rodada=atual.get("rodada", rodada), hoje=hoje, jogos=jogos, outros_hoje=outros,
                historico=avaliar_historico(hist), rodadas_usadas=len(hist))


def _pct(x):
    return f"{round(100 * x)}%"


def gerar_html(dados, css, titulo, agora, nav=""):
    out = [f"<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
           f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>Palpites – {html.escape(titulo)}</title>"
           f"<style>{css} .barra{{display:flex;height:8px;border-radius:4px;overflow:hidden;margin:8px 0 4px}}"
           f".bc{{background:var(--win)}}.be{{background:var(--sub)}}.bf{{background:var(--loss)}}"
           f".lin{{display:flex;justify-content:space-between;font-size:13px;color:var(--sub)}}"
           f".jg{{background:var(--card);border-radius:10px;padding:12px;margin:10px 0}}.jg.h{{border:1px solid var(--acc)}}"
           f".tt{{display:flex;justify-content:space-between;font-weight:600}}</style></head><body>"
           f"<header><h1>Palpites da rodada {dados['rodada']}</h1>"
           f"<div class='sub'>atualizado em {agora} (Brasília)</div>{nav}</header><main>"]
    h = dados.get("historico")
    if h:
        compara = ("Isso é melhor do que" if h["logloss"] < h["logloss_base"] else "Ainda não é melhor do que")
        out.append(f"<p class='sub'>Testado nas rodadas já jogadas (cada uma prevista só com as anteriores): acertou "
                   f"o resultado em <b>{_pct(h['acerto'])}</b> de {h['jogos']} jogos. {compara} usar só a frequência "
                   f"de vitórias, empates e derrotas do campeonato (log-loss {h['logloss']} do modelo contra "
                   f"{h['logloss_base']}; menor é melhor).</p>")
    if dados.get("outros_hoje"):
        out.append("<h2>Hoje em outras competições</h2>")
        for j in dados["outros_hoje"]:
            placar = f" · {j['gc']} x {j['gf']}" if j.get("encerrado") and j.get("gc") is not None else ""
            out.append(f"<div class='jg h'><div class='tt'><span>{html.escape(j['casa'])}</span>"
                       f"<span>{html.escape(j['fora'])}</span></div>")
            p = j.get("previsao")
            if p:
                out.append(f"<div class='barra'><div class='bc' style='width:{100*p['casa']:.0f}%'></div>"
                           f"<div class='be' style='width:{100*p['empate']:.0f}%'></div><div class='bf' style='width:{100*p['fora']:.0f}%'></div></div>"
                           f"<div class='lin'><span>Vitória {_pct(p['casa'])}</span><span>Empate {_pct(p['empate'])}</span>"
                           f"<span>Vitória {_pct(p['fora'])}</span></div>"
                           f"<div class='lin' style='margin-top:4px'><span>Estimativa pela campanha no Brasileirão</span></div>")
            out.append(f"<div class='lin' style='margin-top:6px'><span>{j['hora']}{placar}</span>"
                       f"<span>{html.escape(j['competicao'])}</span></div></div>")
    dia_atual = None
    for j in dados["jogos"]:
        dia = j["data"][:10]
        if dia != dia_atual:
            dia_atual = dia
            try:
                rot = dt.date.fromisoformat(dia).strftime("%d/%m")
            except ValueError:
                rot = dia or "Data a definir"
            out.append(f"<h2>{'Hoje · ' if j['hoje'] else ''}{rot}</h2>")
        p = j["previsao"]
        hora = j["data"][11:16]
        out.append(f"<div class='jg{' h' if j['hoje'] else ''}'><div class='tt'><span>{html.escape(j['casa'])}</span>"
                   f"<span>{html.escape(j['fora'])}</span></div>")
        if p:
            out.append(f"<div class='barra'><div class='bc' style='width:{100*p['casa']:.0f}%'></div>"
                       f"<div class='be' style='width:{100*p['empate']:.0f}%'></div><div class='bf' style='width:{100*p['fora']:.0f}%'></div></div>"
                       f"<div class='lin'><span>Vitória {_pct(p['casa'])}</span><span>Empate {_pct(p['empate'])}</span>"
                       f"<span>Vitória {_pct(p['fora'])}</span></div>"
                       f"<div class='lin' style='margin-top:6px'><span>Placar mais provável: <b style='color:var(--txt)'>{p['placar']}</b></span>"
                       f"<span>Gols esperados {p['gols_casa']:.1f} – {p['gols_fora']:.1f}</span></div>")
        for linha in j.get("contexto", []):
            out.append(f"<div class='lin' style='margin-top:4px'><span>• {html.escape(linha)}</span></div>")
        out.append(f"<div class='lin' style='margin-top:6px'><span>{hora}</span><span>{html.escape(j.get('local') or '')}</span></div></div>")
    out.append("<p class='sub'>Modelo de Poisson com força de ataque e defesa de cada time em casa e fora, relativa à média "
               "do campeonato. Desfalques (status do Cartola: contundido ou suspenso, só titulares habituais) e jogos em outras "
               "competições (ESPN) aparecem como contexto, mas não mudam as porcentagens: testados na temporada 2026, "
               "não melhoraram o acerto.</p>"
               "</main></body></html>")
    return "".join(out)


def gerar(get_publico, saida, css, titulo, agora, cache_path, nav=""):
    status = get_publico("mercado/status")
    ext = None
    try:
        import fontes_externas
        ext = fontes_externas.atualizar_cache(Path(cache_path).parent / "outras_competicoes.json")
        print("  ESPN:", ext.get("_meta"), {k: len(v) for k, v in ext.items() if k != "_meta"})
    except Exception as e:
        print(f"  aviso: dados ESPN indisponíveis ({e})")
    dados = montar(get_publico, status, cache_path, ext)
    saida = Path(saida)
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "palpites.html").write_text(gerar_html(dados, css, titulo, agora, nav), encoding="utf-8")
    sem_data = {k: v for k, v in dados.items() if k != "hoje"}
    (saida / "palpites.json").write_text(json.dumps(sem_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dados
