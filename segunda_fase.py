"""
Segunda fase da liga: duas chaves de 8 times (pontos corridos, 7 rodadas) + final.

  Rodadas 31-37  -> cada time enfrenta os outros 7 da sua chave uma vez (confronto
                    direto: quem fizer mais pontos no Cartola na rodada vence).
  Rodada 38      -> 1º x 2º (final), 3º x 4º, 5º x 6º e 7º x 8º em cada chave.

Uso:
  python segunda_fase.py ids          # uma vez: busca os time_id na liga (precisa do config.txt)
  python segunda_fase.py atualizar    # busca pontuações (endpoints públicos) e gera docs/
  python segunda_fase.py tabela       # imprime os confrontos das 7 rodadas
  python segunda_fase.py simular      # testa tudo com pontuações aleatórias (sem internet)

Só o passo "ids" usa autenticação (config.txt + class_api.py). Depois disso o
script usa apenas endpoints públicos, então o GitHub Actions roda sem token.
"""
import datetime as dt
import html
import json
import random
import sys
import unicodedata
from pathlib import Path

BASE = Path(__file__).resolve().parent
CONFIG = BASE / "segunda_fase" / "config_fase2.json"
CACHE = BASE / "segunda_fase" / "pontuacoes.json"
ESCALACOES = BASE / "segunda_fase" / "escalacoes.json"      # rodadas fechadas: {rodada: {time_id: escalação}}
EXECUCAO = BASE / "segunda_fase" / "ultima_execucao.json"
SAIDA = BASE / "docs"
API = "https://api.cartola.globo.com/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "X-GLB-APP": "cartola_web",
}


# ---------------------------------------------------------------- dados

def carregar(caminho, padrao=None):
    if caminho.exists():
        return json.loads(caminho.read_text(encoding="utf-8"))
    return padrao


def salvar(caminho, dados):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def get_publico(query):
    import requests
    r = requests.get(API + query, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def normalizar(s):
    s = "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")
    return " ".join(s.lower().replace(".", " ").split())


# ---------------------------------------------------------------- tabela de jogos

def confrontos(seeds):
    """Método do círculo: 7 rodadas, todos contra todos uma vez.
    Rodada 1 = 1x8, 2x7, 3x6, 4x5. O confronto 1x2 fica para a última rodada."""
    arr, n, rodadas = list(seeds), len(seeds), []
    for _ in range(n - 1):
        rodadas.append([(arr[i], arr[n - 1 - i]) for i in range(n // 2)])
        arr = [arr[0], arr[-1]] + arr[1:-1]
    idx = next(i for i, r in enumerate(rodadas) if (1, 2) in r or (2, 1) in r)
    rodadas.append(rodadas.pop(idx))
    return rodadas


# ---------------------------------------------------------------- pontuações

def rodadas_encerradas(status):
    """Rodadas com pontuação final. status_mercado: 1 aberto, 2 fechado (rodada em
    andamento), 4 manutenção, 6 temporada encerrada."""
    atual, mercado = status["rodada_atual"], status["status_mercado"]
    ultima = atual if mercado == 6 else atual - 1
    em_andamento = atual if mercado in (2, 4) else None   # 4 = rodada acabando de ser fechada
    return ultima, em_andamento


def buscar_ids_publico(cfg):
    """Preenche time_id pela busca pública do Cartola (times?q=), sem token.
    Só aceita um resultado cujo nome do time E do cartoleiro batam com o config."""
    from urllib.parse import quote
    mudou = False
    for chave in cfg["chaves"]:
        for t in chave["times"]:
            if t.get("time_id"):
                continue
            nome, dono = normalizar(t["nome"]), normalizar(t.get("cartoleiro", ""))
            consultas = [t["nome"], " ".join(t["nome"].split()[:2]), t["nome"].split()[0]]
            for q in dict.fromkeys(consultas):
                try:
                    res = get_publico("times?q=" + quote(q))
                except Exception as e:
                    print(f"  busca '{q}' falhou: {e}")
                    continue
                res = res if isinstance(res, list) else res.get("times", [])
                achou = [m for m in res if normalizar(m.get("nome")).startswith(nome)
                         and normalizar(m.get("nome_cartola")).startswith(dono)]
                if len(achou) == 1:
                    m = achou[0]
                    t.update(time_id=m["time_id"], nome=m["nome"], cartoleiro=m.get("nome_cartola", t["cartoleiro"]))
                    print(f"  ok  {t['nome']:<28} {t['time_id']}")
                    mudou = True
                    break
            else:
                print(f"  ??  {t['nome']}: não encontrado na busca pública")
    if mudou:
        salvar(CONFIG, cfg)


def buscar_pontuacoes(cfg, ultima):
    import parciais
    cache = carregar(CACHE, {})
    escalacoes = carregar(ESCALACOES, {})
    times = [t for c in cfg["chaves"] for t in c["times"]]
    if any(not t.get("time_id") for t in times):
        buscar_ids_publico(cfg)
    sem_id = [t["nome"] for t in times if not t.get("time_id")]
    if sem_id:
        sys.exit(f"Faltam time_id para: {', '.join(sem_id)}. Preencha à mão em "
                 f"segunda_fase/config_fase2.json ou rode 'python segunda_fase.py ids'.")
    rodadas = cfg["rodadas_grupo"] + [cfg["rodada_final"]]
    for r in rodadas:
        if r > ultima:
            continue
        ja = cache.setdefault(str(r), {})
        esc = escalacoes.setdefault(str(r), {})
        for t in times:
            tid = str(t["time_id"])
            if tid in ja and tid in esc:
                continue
            try:
                d = get_publico(f"time/id/{tid}/{r}")
                ja[tid] = round(float(d.get("pontos") or 0), 2)
                esc[tid] = parciais.de_rodada_fechada(d)
                esc[tid]["pontos"] = ja[tid]          # vale o total oficial
            except Exception as e:  # time não escalado / erro pontual: tenta de novo na próxima execução
                print(f"  aviso: rodada {r}, {t['nome']}: {e}")
        if esc and str(r) not in escalacoes.get("_clubes_rodadas", []):
            try:
                escalacoes.setdefault("_clubes", {}).update(
                    {str(k): v for k, v in parciais.clubes_abrev(get_publico(f"partidas/{r}")).items()})
                escalacoes.setdefault("_clubes_rodadas", []).append(str(r))
            except Exception as e:
                print(f"  aviso: clubes da rodada {r}: {e}")
    salvar(CACHE, cache)
    salvar(ESCALACOES, escalacoes)
    return cache


# ---------------------------------------------------------------- classificação

def calcular(cfg, pontos):
    """pontos: {"31": {"<time_id ou seed-key>": 54.3, ...}, ...}"""
    pv, pe = cfg["pontos"]["vitoria"], cfg["pontos"]["empate"]
    chaves = []
    for chave in cfg["chaves"]:
        por_seed = {t["seed"]: t for t in chave["times"]}
        chave_tid = lambda s: str(por_seed[s]["time_id"])  # noqa: E731
        tab = {s: dict(time=t, P=0, J=0, V=0, E=0, D=0, PC=0.0) for s, t in por_seed.items()}
        rodadas = []
        for rodada, jogos in zip(cfg["rodadas_grupo"], confrontos(sorted(por_seed))):
            pts = pontos.get(str(rodada), {})
            lista = []
            for a, b in jogos:
                pa, pb = pts.get(chave_tid(a)), pts.get(chave_tid(b))
                lista.append(dict(a=a, b=b, pa=pa, pb=pb))
                if pa is None or pb is None:
                    continue
                for s, meu, outro in ((a, pa, pb), (b, pb, pa)):
                    t = tab[s]
                    t["J"] += 1
                    t["PC"] = round(t["PC"] + meu, 2)
                    if meu > outro:
                        t["V"] += 1; t["P"] += pv
                    elif meu == outro:
                        t["E"] += 1; t["P"] += pe
                    else:
                        t["D"] += 1
            rodadas.append(dict(rodada=rodada, jogos=lista))
        # Desempate: pontos, vitórias, pontos do Cartola na fase, campanha na 1ª fase.
        ordem = sorted(tab, key=lambda s: (-tab[s]["P"], -tab[s]["V"], -tab[s]["PC"], s))
        classificacao = [dict(pos=i + 1, seed=s, **tab[s]) for i, s in enumerate(ordem)]

        # Rodada 38: 1x2 (final), 3x4, 5x6, 7x8. Empate -> vence o melhor colocado na fase.
        fase_completa = all(t["J"] == 7 for t in tab.values())
        pts38 = pontos.get(str(cfg["rodada_final"]), {})
        decisoes = []
        for i, titulo in enumerate(["Final", "3º lugar", "5º lugar", "7º lugar"]):
            sa, sb = (ordem[2 * i], ordem[2 * i + 1]) if fase_completa else (None, None)
            pa = pts38.get(chave_tid(sa)) if sa else None
            pb = pts38.get(chave_tid(sb)) if sb else None
            venc = None
            if pa is not None and pb is not None:
                venc = sb if pb > pa else sa
            decisoes.append(dict(titulo=titulo, pos=(2 * i + 1, 2 * i + 2), a=sa, b=sb, pa=pa, pb=pb, vencedor=venc))
        final_pos = None
        if all(d["vencedor"] for d in decisoes):
            final_pos = []
            for d in decisoes:
                final_pos += [d["vencedor"], d["b"] if d["vencedor"] == d["a"] else d["a"]]
        chaves.append(dict(id=chave["id"], nome=chave["nome"], times=por_seed, rodadas=rodadas,
                           classificacao=classificacao, decisoes=decisoes, final=final_pos))
    return chaves


# ---------------------------------------------------------------- página

CSS = """
:root{--bg:#1b1d22;--card:#24272e;--line:#33373f;--txt:#f2f2f2;--sub:#9aa0aa;--acc:#f47b20;--win:#2fbf71;--loss:#e5484d}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:15px/1.4 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{background:#000;padding:18px 16px}h1{margin:0;font-size:22px;letter-spacing:.5px}
.sub{color:var(--sub);font-size:13px}main{max-width:900px;margin:auto;padding:16px}
h2{font-size:18px;margin:28px 0 10px;color:var(--acc)}h3{font-size:15px;margin:18px 0 8px}
table{width:100%;border-collapse:collapse;background:var(--card);border-radius:10px;overflow:hidden}
th,td{padding:8px 6px;text-align:center;border-bottom:1px solid var(--line)}th{color:var(--sub);font-weight:600;font-size:12px}
td.n{text-align:left}td.n small{display:block;color:var(--sub)}tr.z td{background:rgba(244,123,32,.10)}
.jogos{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px}
.r{background:var(--card);border-radius:10px;padding:10px 12px}.r b{color:var(--acc)}
.j{display:flex;justify-content:space-between;gap:8px;padding:4px 0;border-top:1px solid var(--line)}
.j:first-of-type{border-top:0}.w{color:var(--win);font-weight:700}.l{color:var(--sub)}
.tag{font-size:11px;color:var(--bg);background:var(--acc);border-radius:4px;padding:1px 6px;margin-left:6px}
.camp{background:linear-gradient(135deg,#3a2a12,#24272e);border:1px solid var(--acc);border-radius:12px;padding:14px;margin:10px 0}
.scroll{overflow-x:auto}
a.tl{color:inherit;text-decoration:none;border-bottom:1px dotted var(--sub)}
.cta{display:block;margin:4px 0 8px;padding:14px 16px;border-radius:12px;background:var(--acc);color:#111;font-weight:700;text-decoration:none;font-size:16px}
.cta small{display:block;font-weight:500;font-size:13px;opacity:.8}
"""


def nome(t):
    from escalacoes import link
    return f"{link(t)}<small>{html.escape(t.get('cartoleiro', ''))}</small>"


def fmt(p):
    return "–" if p is None else f"{p:.2f}"


def jogo_html(times, a, b, pa, pb):
    ca = cb = ""
    if pa is not None and pb is not None:
        ca, cb = ("w", "l") if pa > pb else (("l", "w") if pb > pa else ("", ""))
    from escalacoes import link
    return (f'<div class="j"><span class="{ca}">{link(times[a])} {fmt(pa)}</span>'
            f'<span class="{cb}">{fmt(pb)} {link(times[b])}</span></div>')


def agora_brasilia():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).strftime("%d/%m/%Y %H:%M")


NAV = ("<nav style='margin-top:8px'>"
       "<a style='color:var(--acc);margin-right:14px' href='index.html'>Classificação</a>"
       "<a style='color:var(--acc);margin-right:14px' href='sugestoes.html'>Sugestões</a>"
       "<a style='color:var(--acc)' href='palpites.html'>Palpites</a></nav>")


def ao_vivo_html(c, rodada, parciais):
    """Cartão da rodada em andamento, no topo da chave."""
    r = next((x for x in c["rodadas"] if x["rodada"] == rodada), None)
    if r is None:
        jogos = [dict(a=d["a"], b=d["b"], pa=d["pa"], pb=d["pb"]) for d in c["decisoes"] if d["a"]]
        titulo = f"Rodada {rodada} · decisões ao vivo"
    else:
        jogos, titulo = r["jogos"], f"Rodada {rodada} · ao vivo"
    if not jogos:
        return ""
    times = c["times"]
    from escalacoes import link

    def linha(seed, pts, classe):
        p = parciais.get(str(times[seed].get("time_id")))
        jog = f"<small class='sub'> {p['jogaram']}/{p['escalados']}</small>" if p else ""
        return (f"<div style='display:flex;justify-content:space-between;gap:8px'>"
                f"<span class='{classe}'>{link(times[seed])}</span>"
                f"<span style='white-space:nowrap'><span class='{classe}'>{fmt(pts)}</span>{jog}</span></div>")
    out = [f"<div class='r' style='border:1px solid var(--acc);margin-bottom:14px'><b>{titulo}</b>"]
    for j in jogos:
        a, b, pa, pb = j["a"], j["b"], j["pa"], j["pb"]
        ca = cb = ""
        if pa is not None and pb is not None and pa != pb:
            ca, cb = ("w", "l") if pa > pb else ("l", "w")
        out.append("<div style='padding:6px 0;border-top:1px solid var(--line)'>"
                   + linha(a, pa, ca) + linha(b, pb, cb) + "</div>")
    out.append("<div class='sub' style='margin-top:6px'>Parcial calculada com os pontos ao vivo do Cartola "
               "(capitão 1,5× e reservas). O número menor mostra quantos titulares já jogaram. "
               "O total oficial sai quando a rodada fecha.</div></div>")
    return "".join(out)


def gerar_html(cfg, chaves, ultima, em_andamento, parciais=None):
    agora = agora_brasilia()
    parciais = parciais or {}
    situacao = (f"Rodada {em_andamento} em andamento · classificação com parciais ao vivo" if em_andamento and parciais
                else f"Rodada {em_andamento} em andamento" if em_andamento else f"Última rodada encerrada: {ultima}")
    out = [f"<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
           f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
           f"<title>{html.escape(cfg['nome_torneio'])}</title><style>{CSS}</style></head><body>"
           f"<header><h1>{html.escape(cfg['nome_torneio'])}</h1>"
           f"<div class='sub'>{situacao} · atualizado em {agora} (Brasília)</div>{NAV}</header><main>"
           f"<a class='cta' href='sugestoes.html'>Ver sugestões de escalação →"
           f"<small>Melhor time por orçamento, destaques por posição e custo-benefício</small></a>"]
    for c in chaves:
        times = c["times"]
        out.append(f"<h2>{html.escape(c['nome'])}</h2>")
        if em_andamento and parciais:
            out.append(ao_vivo_html(c, em_andamento, parciais))
        if c["final"]:
            camp = times[c["final"][0]]
            out.append(f"<div class='camp'>🏆 Campeão: <b>{html.escape(camp['nome'])}</b> "
                       f"({html.escape(camp.get('cartoleiro', ''))})</div>")
        out.append("<div class='scroll'><table><tr><th>#</th><th style='text-align:left'>Time</th>"
                   "<th>P</th><th>J</th><th>V</th><th>E</th><th>D</th><th>PC</th></tr>")
        for t in c["classificacao"]:
            z = " class='z'" if t["pos"] <= 2 else ""
            out.append(f"<tr{z}><td>{t['pos']}º</td><td class='n'>{nome(t['time'])}</td><td><b>{t['P']}</b></td>"
                       f"<td>{t['J']}</td><td>{t['V']}</td><td>{t['E']}</td><td>{t['D']}</td><td>{t['PC']:.2f}</td></tr>")
        out.append("</table></div><h3>Rodada 38 – decisões</h3><div class='jogos'><div class='r'>")
        for d in c["decisoes"]:
            out.append(f"<b>{d['titulo']}</b> <span class='sub'>({d['pos'][0]}º x {d['pos'][1]}º)</span>")
            if d["a"]:
                out.append(jogo_html(times, d["a"], d["b"], d["pa"], d["pb"]))
            else:
                out.append("<div class='j sub'>Definido após a rodada 37</div>")
        out.append("</div></div><h3>Jogos</h3><div class='jogos'>")
        for r in c["rodadas"]:
            tag = "<span class='tag'>ao vivo</span>" if r["rodada"] == em_andamento else ""
            out.append(f"<div class='r'><b>Rodada {r['rodada']}</b>{tag}")
            out += [jogo_html(times, j["a"], j["b"], j["pa"], j["pb"]) for j in r["jogos"]]
            out.append("</div>")
        out.append("</div>")
    out.append("<p class='sub'>Vitória 3, empate 1. Desempate: pontos, vitórias, pontos do Cartola na fase, "
               "campanha na 1ª fase. Na rodada 38, empate favorece o melhor colocado da chave. "
               "Toque no nome de um time para ver a escalação de cada rodada.</p></main></body></html>")
    return "".join(out)


def publicar(cfg, chaves, ultima, em_andamento, parciais=None):
    SAIDA.mkdir(exist_ok=True)
    (SAIDA / "index.html").write_text(gerar_html(cfg, chaves, ultima, em_andamento, parciais), encoding="utf-8")
    resumo = {c["id"]: [dict(pos=t["pos"], nome=t["time"]["nome"], P=t["P"], J=t["J"], V=t["V"], E=t["E"],
                             D=t["D"], PC=t["PC"]) for t in c["classificacao"]] for c in chaves}
    salvar(SAIDA / "fase2.json", dict(ultima_rodada=ultima, em_andamento=em_andamento, parciais=parciais or {},
                                      chaves=resumo))


# ---------------------------------------------------------------- comandos

def cmd_ids(cfg):
    import class_api
    linhas = [l.rstrip() for l in open(BASE / "config.txt", encoding="utf-8")]
    api = class_api.API(linhas[1], linhas[0])
    query = linhas[3] if len(linhas) > 3 else linhas[2]  # mesma consulta da liga usada no base_routine.py
    membros = api.request_api(query)["times"]
    for chave in cfg["chaves"]:
        for t in chave["times"]:
            alvo = normalizar(t["nome"])
            achou = [m for m in membros if normalizar(m.get("nome")).startswith(alvo)]
            if len(achou) == 1:
                m = achou[0]
                t.update(time_id=m["time_id"], nome=m["nome"], cartoleiro=m.get("nome_cartola", t["cartoleiro"]))
                print(f"  ok  {t['nome']:<28} {t['time_id']}")
            else:
                print(f"  ??  {t['nome']:<28} {len(achou)} resultados – preencha time_id à mão")
    salvar(CONFIG, cfg)


BRT = dt.timezone(dt.timedelta(hours=-3))
JANELA_JOGO = dt.timedelta(hours=4)       # ~2 h de jogo + 2 h depois que acaba
INTERVALO_SEM_JOGO = dt.timedelta(hours=3)


def cmd_decidir(agora=None):
    """Decide se esta execução agendada (a cada 15 min) deve atualizar:
    sim durante jogos (do apito inicial até 4 h depois); fora disso, a cada 3 h."""
    agora = agora or dt.datetime.now(dt.timezone.utc)
    motivo = None
    try:
        for p in get_publico("partidas").get("partidas", []):
            if p.get("valida") is False:
                continue
            if p.get("status_transmissao_tr") == "EM_ANDAMENTO":
                motivo = "jogo em andamento"
                break
            if p.get("partida_data"):
                ini = dt.datetime.fromisoformat(p["partida_data"].replace(" ", "T")).replace(tzinfo=BRT)
                if ini - dt.timedelta(minutes=15) <= agora <= ini + JANELA_JOGO:
                    motivo = f"horário de jogo ({ini:%d/%m %H:%M})"
                    break
    except Exception as e:
        motivo = f"não foi possível ler os jogos ({e})"
    if motivo is None:
        try:
            ultima = dt.datetime.fromisoformat(carregar(EXECUCAO, {})["em"])
        except (KeyError, ValueError, TypeError):
            ultima = None
        # 10 min de folga: o agendador do GitHub costuma atrasar alguns minutos
        if ultima is None or agora - ultima >= INTERVALO_SEM_JOGO - dt.timedelta(minutes=10):
            motivo = "3 horas desde a última atualização"
    rodar = motivo is not None
    print(f"rodar={'sim' if rodar else 'não'} ({motivo or 'sem jogos, última atualização recente'})")
    import os
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rodar={'true' if rodar else 'false'}\n")
    return rodar


def cmd_tabela(cfg):
    for c in cfg["chaves"]:
        t = {x["seed"]: x["nome"] for x in c["times"]}
        print(f"\n{c['nome']}")
        for rodada, jogos in zip(cfg["rodadas_grupo"], confrontos(sorted(t))):
            print(f"  R{rodada}: " + " | ".join(f"{t[a]} x {t[b]}" for a, b in jogos))


def cmd_atualizar(cfg):
    ultima, em_andamento = rodadas_encerradas(get_publico("mercado/status"))
    pontos = buscar_pontuacoes(cfg, ultima)
    parc, clubes = {}, {}
    rodadas_fase = cfg["rodadas_grupo"] + [cfg["rodada_final"]]
    if em_andamento in rodadas_fase:
        import parciais
        ids = [t["time_id"] for c in cfg["chaves"] for t in c["times"] if t.get("time_id")]
        try:
            parc, acabou, clubes = parciais.calcular(get_publico, ids)
            # parciais não vão para o cache: só a pontuação oficial fica salva
            pontos = {**pontos, str(em_andamento): {k: v["pontos"] for k, v in parc.items()}}
            print(f"Parciais da rodada {em_andamento}: {len(parc)} times" + (" (todos os jogos encerrados)" if acabou else ""))
        except Exception as e:
            print(f"aviso: parciais indisponíveis ({e})")
    resumo_parc = {k: {c: v[c] for c in ("pontos", "jogaram", "escalados")} for k, v in parc.items()}
    publicar(cfg, calcular(cfg, pontos), ultima, em_andamento, resumo_parc)
    gerar_paginas_times(cfg, parc, clubes, em_andamento)
    print(f"docs/ atualizado (última rodada encerrada: {ultima}).")
    gerar_sugestoes(cfg, get_publico, SAIDA)
    gerar_palpites(cfg, get_publico, SAIDA)
    salvar(EXECUCAO, {"em": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")})


def gerar_palpites(cfg, fonte, saida):
    try:
        import palpites
        d = palpites.gerar(fonte, saida, CSS, cfg["nome_torneio"], agora_brasilia(),
                           BASE / "segunda_fase" / "partidas_cache.json", NAV)
        print(f"Palpites gerados: {len(d['jogos'])} jogos, histórico {d['historico']}.")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"aviso: palpites não gerados ({e})")


def gerar_paginas_times(cfg, parc, clubes, em_andamento):
    try:
        import escalacoes
        fechadas = carregar(ESCALACOES, {})
        mapa_clubes = {**fechadas.get("_clubes", {}), **{str(k): v for k, v in clubes.items()}}
        por_rodada = {r: v for r, v in fechadas.items() if not r.startswith("_")}
        if parc and em_andamento:
            por_rodada[str(em_andamento)] = parc
        escalacoes.gerar(cfg, por_rodada, mapa_clubes, SAIDA, CSS, NAV, em_andamento, agora_brasilia())
        salvar(SAIDA / "escalacoes.json", {"ao_vivo": em_andamento, "rodadas": por_rodada})
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"aviso: páginas dos times não geradas ({e})")


def gerar_sugestoes(cfg, fonte, saida):
    """Não derruba a classificação se a parte de sugestões falhar."""
    try:
        import sugestoes
        d = sugestoes.gerar(fonte, saida, CSS, cfg["nome_torneio"], agora_brasilia(),
                            cfg.get("orcamentos", [100, 140, 180]), NAV)
        print(f"Sugestões geradas: {d['jogadores_avaliados']} jogadores avaliados.")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"aviso: sugestões não geradas ({e})")


def cmd_simular(cfg, ate=38):
    rnd = random.Random(2026)
    for i, c in enumerate(cfg["chaves"]):
        for t in c["times"]:
            t["time_id"] = t["time_id"] or 1000 * (i + 1) + t["seed"]
    rodadas = [r for r in cfg["rodadas_grupo"] + [cfg["rodada_final"]] if r <= ate]
    pontos = {str(r): {str(t["time_id"]): round(rnd.uniform(30, 110), 2)
                       for c in cfg["chaves"] for t in c["times"]} for r in rodadas}
    global SAIDA
    SAIDA = BASE / "segunda_fase" / "simulacao"
    publicar(cfg, calcular(cfg, pontos), ate, None)
    print(f"Simulação gerada em {SAIDA}/index.html")


if __name__ == "__main__":
    cfg = carregar(CONFIG)
    acao = sys.argv[1] if len(sys.argv) > 1 else "atualizar"
    if acao == "decidir":
        cmd_decidir()
    elif acao == "ids":
        cmd_ids(cfg)
    elif acao == "tabela":
        cmd_tabela(cfg)
    elif acao == "simular":
        cmd_simular(cfg, int(sys.argv[2]) if len(sys.argv) > 2 else 38)
    else:
        cmd_atualizar(cfg)
