"""
Parciais ao vivo de cada time durante a rodada, só com dados públicos do Cartola.

Durante a rodada o Cartola não publica o total de cada time, então calculamos:
  - titulares: pontos ao vivo de `atletas/pontuados`;
  - capitão vale 1,5× (conferido com os totais oficiais da rodada 30);
  - reserva entra no lugar do titular da mesma posição que não jogou, quando o
    jogo do titular já acabou (ou não vale para a rodada);
  - reserva de luxo troca com o titular de pior pontuação da posição dele, se
    pontuou mais, depois que todos os jogos da rodada terminaram.
É uma estimativa: o total oficial sai quando o Cartola fecha a rodada.
"""
CAPITAO = 1.5
ENCERRADO = {"ENCERRADA", "POS_JOGO", "FINALIZADO", "ENCERRADO"}


def _status_clubes(partidas):
    """{clube_id: 'encerrado' | 'invalido' | 'pendente'}"""
    st = {}
    for p in partidas.get("partidas", []):
        if p.get("valida") is False:
            s = "invalido"
        elif (p.get("status_transmissao_tr") in ENCERRADO) or (p.get("periodo_tr") in ENCERRADO):
            s = "encerrado"
        else:
            s = "pendente"
        st[p["clube_casa_id"]] = st[p["clube_visitante_id"]] = s
    return st


def calcular_time(time, pontuados, status_clubes, rodada_acabou):
    """Parcial de um time. `time` = resposta de time/id/{id} com o mercado fechado."""
    pts = {int(k): v for k, v in (pontuados.get("atletas") or {}).items()}

    def jogou(a):
        p = pts.get(int(a["atleta_id"]))
        return p is not None and p.get("entrou_em_campo", True)

    def valor(a):
        p = pts.get(int(a["atleta_id"]))
        return float(p.get("pontuacao") or 0) if p and p.get("entrou_em_campo", True) else 0.0

    def fora_de_vez(a):
        """Titular que já não pode mais pontuar."""
        s = status_clubes.get(a.get("clube_id"))
        return not jogou(a) and s in ("encerrado", "invalido")

    titulares = list(time.get("atletas") or [])
    reservas = list(time.get("reservas") or [])
    luxo_id = time.get("reserva_luxo_id")
    capitao = time.get("capitao_id")
    usados = set()
    linhas = []
    for a in titulares:
        efetivo = a
        if fora_de_vez(a):
            sub = next((r for r in reservas if r.get("posicao_id") == a.get("posicao_id")
                        and r["atleta_id"] not in usados and jogou(r)), None)
            if sub:
                usados.add(sub["atleta_id"])
                efetivo = sub
        linhas.append(dict(titular=a, efetivo=efetivo, pontos=valor(efetivo)))

    if rodada_acabou and luxo_id:
        luxo = next((r for r in reservas if r["atleta_id"] == luxo_id and r["atleta_id"] not in usados), None)
        if luxo and jogou(luxo):
            mesma = [l for l in linhas if l["efetivo"].get("posicao_id") == luxo.get("posicao_id")
                     and l["efetivo"] is l["titular"]]
            if mesma:
                pior = min(mesma, key=lambda l: l["pontos"])
                if valor(luxo) > pior["pontos"]:
                    pior.update(efetivo=luxo, pontos=valor(luxo))

    def nome(a):
        p = pts.get(int(a["atleta_id"])) or {}
        return a.get("apelido") or p.get("apelido") or str(a["atleta_id"])

    def situacao(a):
        if jogou(a):
            return "jogou"
        s = status_clubes.get(a.get("clube_id"))
        return "nao_jogou" if s in ("encerrado", "invalido") else "a_jogar"

    total = 0.0
    jogadores = []
    for l in linhas:
        cap = l["titular"]["atleta_id"] == capitao and l["efetivo"] is l["titular"]
        mult = CAPITAO if cap else 1.0
        total += l["pontos"] * mult
        t, e = l["titular"], l["efetivo"]
        jogadores.append(dict(
            nome=nome(t), pos=t.get("posicao_id"), clube=t.get("clube_id"), capitao=t["atleta_id"] == capitao,
            situacao=situacao(t), pontos=round(valor(t) * (CAPITAO if cap else 1.0), 2),
            entrou=None if e is t else dict(nome=nome(e), clube=e.get("clube_id"), pontos=round(l["pontos"], 2),
                                            luxo=e["atleta_id"] == luxo_id)))
    ids_entraram = {l["efetivo"]["atleta_id"] for l in linhas}
    banco = [dict(nome=nome(r), pos=r.get("posicao_id"), clube=r.get("clube_id"), luxo=r["atleta_id"] == luxo_id,
                  situacao=situacao(r), pontos=round(valor(r), 2), entrou=r["atleta_id"] in ids_entraram)
             for r in reservas]
    jogaram = sum(1 for l in linhas if jogou(l["efetivo"]))
    return dict(pontos=round(total, 2), jogaram=jogaram, escalados=len(titulares),
                jogadores=jogadores, banco=banco)


def de_rodada_fechada(time):
    """Mesma análise para uma rodada já fechada (resposta de time/id/{id}/{rodada}),
    que traz os pontos e se cada jogador entrou em campo."""
    pts = {"atletas": {str(a["atleta_id"]): dict(pontuacao=a.get("pontos_num") or 0, apelido=a.get("apelido"),
                                                 entrou_em_campo=bool(a.get("entrou_em_campo")))
                       for a in (time.get("atletas") or []) + (time.get("reservas") or [])
                       if a.get("entrou_em_campo")}}
    clubes = {a.get("clube_id"): "encerrado" for a in (time.get("atletas") or []) + (time.get("reservas") or [])}
    return calcular_time(time, pts, clubes, True)


def clubes_abrev(partidas):
    return {int(k): (v.get("abreviacao") or v.get("nome") or k) for k, v in (partidas.get("clubes") or {}).items()}


def calcular(get_publico, time_ids):
    """({time_id: {pontos, jogaram, escalados, jogadores, banco}}, rodada_acabou, siglas dos clubes)."""
    pontuados = get_publico("atletas/pontuados")
    partidas = get_publico("partidas")
    st = _status_clubes(partidas)
    validos = [s for s in st.values() if s != "invalido"]
    acabou = bool(validos) and all(s == "encerrado" for s in validos)
    out = {}
    for tid in time_ids:
        try:
            out[str(tid)] = calcular_time(get_publico(f"time/id/{tid}"), pontuados, st, acabou)
        except Exception as e:
            print(f"  aviso: parcial do time {tid}: {e}")
    return out, acabou, clubes_abrev(partidas)
