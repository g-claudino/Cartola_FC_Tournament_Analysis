"""
Dados públicos de fora do Cartola para os palpites:

1. Jogos dos clubes em outras competições (Copa do Brasil, Libertadores,
   Sul-Americana) pelo placar público da ESPN, sem chave de API.
2. Desfalques pelo status dos jogadores no próprio Cartola (atletas/mercado):
   contundido e suspenso = fora; dúvida = meio desfalque.

Os times da ESPN são ligados aos clubes do Cartola comparando o calendário do
Brasileirão (data + mando) das duas fontes, sem depender da grafia dos nomes.
"""
import datetime as dt
import json
from pathlib import Path

ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer/{liga}/scoreboard?dates={dia}"  # só aceita um dia por vez
LIGA_BR = "bra.1"
OUTRAS = {
    "bra.copa_do_brazil": "Copa do Brasil",
    "conmebol.libertadores": "Libertadores",
    "conmebol.sudamericana": "Sul-Americana",
}
TEMPORADA_INICIO = dt.date(2026, 1, 1)


_SESSAO = None


def _get(url):
    global _SESSAO
    import requests
    if _SESSAO is None:
        _SESSAO = requests.Session()
        _SESSAO.headers["User-Agent"] = "Mozilla/5.0"
    r = _SESSAO.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def _eventos(liga, dia):
    d = _get(ESPN.format(liga=liga, dia=dia.strftime("%Y%m%d")))
    out = {}
    for ev in d.get("events", []):
        comp = (ev.get("competitions") or [{}])[0]
        lados = {c.get("homeAway"): c for c in comp.get("competitors", [])}
        if "home" not in lados or "away" not in lados:
            continue
        st = (ev.get("status") or comp.get("status") or {}).get("type", {})
        def placar(c):
            try:
                return int(float(c.get("score"))) if st.get("completed") else None
            except (TypeError, ValueError):
                return None
        out[str(ev["id"])] = dict(
            data=ev.get("date") or comp.get("date"),
            casa=str(lados["home"]["team"]["id"]), casa_nome=lados["home"]["team"].get("displayName"),
            fora=str(lados["away"]["team"]["id"]), fora_nome=lados["away"]["team"].get("displayName"),
            gc=placar(lados["home"]), gf=placar(lados["away"]), encerrado=bool(st.get("completed")),
        )
    return out


def atualizar_cache(cache_path, hoje=None):
    """Baixa a temporada inteira na primeira vez (um pedido por dia e competição);
    depois só os últimos 10 dias e as próximas 3 semanas."""
    from concurrent.futures import ThreadPoolExecutor
    cache_path = Path(cache_path)
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    hoje = hoje or dt.date.today()
    fim = hoje + dt.timedelta(days=21)
    meta = cache.setdefault("_meta", {})
    tarefas = []
    for liga in [LIGA_BR, *OUTRAS]:
        cache.setdefault(liga, {})
        ini = TEMPORADA_INICIO if meta.get(liga) != "ok" else hoje - dt.timedelta(days=10)
        tarefas += [(liga, ini + dt.timedelta(days=i)) for i in range((fim - ini).days + 1)]
    erros = {}
    def baixar(t):
        try:
            return t, _eventos(*t), None
        except Exception as e:
            return t, {}, str(e)[:120]
    with ThreadPoolExecutor(max_workers=8) as ex:
        for (liga, dia), evs, err in ex.map(baixar, tarefas):
            cache[liga].update(evs)
            if err:
                erros.setdefault(liga, []).append(f"{dia}: {err}")
    for liga in [LIGA_BR, *OUTRAS]:
        n_err = len(erros.get(liga, []))
        meta[liga] = "ok" if n_err == 0 else f"{n_err} dias com erro, ex.: {erros[liga][0]}"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return cache


# ---------------------------------------------------------------- ligação ESPN → Cartola

def _dia(iso):
    """Dia no horário de Brasília (a ESPN usa UTC: jogo às 21h30 cai no dia seguinte)."""
    try:
        t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return (iso or "")[:10]
    if t.tzinfo is None:
        return t.date().isoformat()
    return t.astimezone(dt.timezone(dt.timedelta(hours=-3))).date().isoformat()


def mapear_times(cache, jogos_cartola):
    """jogos_cartola: {rodada: [{casa, fora, data}]}. Devolve {espn_id: clube_id_cartola}.
    Cada time é reconhecido pelo seu calendário (data, mandante?) no Brasileirão."""
    def assinatura_espn():
        s = {}
        for j in cache.get(LIGA_BR, {}).values():
            for t, casa in ((j["casa"], True), (j["fora"], False)):
                s.setdefault(t, set()).add((_dia(j["data"]), casa))
        return s
    def assinatura_cartola():
        s = {}
        for jogos in jogos_cartola.values():
            for j in jogos:
                if not j.get("data"):
                    continue
                for t, casa in ((j["casa"], True), (j["fora"], False)):
                    s.setdefault(t, set()).add((_dia(j["data"]), casa))
        return s
    se, sc = assinatura_espn(), assinatura_cartola()
    pares = []
    for e, a in se.items():
        for c, b in sc.items():
            inter = len(a & b)
            if inter:
                pares.append((inter / len(a | b), e, c))
    mapa, usados = {}, set()
    for sim, e, c in sorted(pares, reverse=True):
        if sim < 0.5 or e in mapa or c in usados:
            continue
        mapa[e] = c
        usados.add(c)
    return mapa


def agenda_outras(cache, mapa):
    """{clube_id_cartola: [(datetime_utc, competicao)]} dos jogos fora do Brasileirão."""
    agenda = {}
    for liga, nome in OUTRAS.items():
        for j in cache.get(liga, {}).values():
            try:
                quando = dt.datetime.fromisoformat(j["data"].replace("Z", "+00:00"))
            except (AttributeError, ValueError):
                continue
            for t in (j["casa"], j["fora"]):
                if t in mapa:
                    agenda.setdefault(mapa[t], []).append((quando, nome))
    for v in agenda.values():
        v.sort()
    return agenda


def calendario(agenda, clube, quando, janela_h=96):
    """Jogo de outra competição até `janela_h` horas antes e depois do jogo do Brasileirão."""
    antes = depois = None
    antes_h = depois_h = None
    for t, nome in agenda.get(clube, []):
        h = (t - quando).total_seconds() / 3600
        if -janela_h <= h < -2:
            antes, antes_h = nome, -h
        elif 2 < h <= janela_h and depois is None:
            depois, depois_h = nome, h
    return dict(antes=antes, antes_h=antes_h, depois=depois, depois_h=depois_h)


def jogos_do_dia(cache, mapa, dia_iso):
    """Jogos de outras competições num dia (horário de Brasília)."""
    out = []
    for liga, nome in OUTRAS.items():
        for j in cache.get(liga, {}).values():
            if _dia(j["data"]) != dia_iso:
                continue
            t = dt.datetime.fromisoformat(j["data"].replace("Z", "+00:00")).astimezone(dt.timezone(dt.timedelta(hours=-3)))
            out.append(dict(competicao=nome, hora=t.strftime("%H:%M"), casa=j["casa_nome"], fora=j["fora_nome"],
                            casa_id=mapa.get(j["casa"]), fora_id=mapa.get(j["fora"]), gc=j.get("gc"), gf=j.get("gf"),
                            encerrado=j.get("encerrado")))
    return sorted(out, key=lambda x: x["hora"])


# ---------------------------------------------------------------- desfalques (status do Cartola)

FORA, DUVIDA = {3, 5}, 2
ATAQUE, DEFESA = {4, 5}, {1, 2, 3}


def desfalques(atletas, rodadas_jogadas):
    """Parcela do time titular habitual que está fora, por clube, separada em ataque e defesa.
    Importância de cada jogador = fração dos jogos que disputou × média (mínimo 1)."""
    soma = {}
    for a in atletas:
        pos, j = a.get("posicao_id"), a.get("jogos_num") or 0
        if pos not in ATAQUE | DEFESA or j < 3 or rodadas_jogadas <= 0:
            continue
        imp = min(j / rodadas_jogadas, 1.0) * max(float(a.get("media_num") or 0), 1.0)
        st = a.get("status_id")
        fora = imp if st in FORA else imp * 0.5 if st == DUVIDA else 0.0
        lado = "ataque" if pos in ATAQUE else "defesa"
        s = soma.setdefault(a["clube_id"], {"ataque": [0.0, 0.0, []], "defesa": [0.0, 0.0, []]})
        s[lado][0] += fora
        s[lado][1] += imp
        if st in FORA and imp >= 1.0:
            s[lado][2].append(a.get("apelido") or a.get("nome"))
    return {c: dict(ataque=s["ataque"][0] / s["ataque"][1] if s["ataque"][1] else 0.0,
                    defesa=s["defesa"][0] / s["defesa"][1] if s["defesa"][1] else 0.0,
                    nomes=s["ataque"][2] + s["defesa"][2])
            for c, s in soma.items()}
