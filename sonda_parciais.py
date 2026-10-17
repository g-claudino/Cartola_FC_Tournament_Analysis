"""Diagnóstico temporário: formato dos dados de rodada em andamento."""
import json
def rodar(get):
    out = {}
    def tenta(k, q, f=lambda x: x):
        try:
            out[k] = f(get(q))
        except Exception as e:
            out[k] = {"erro": str(e)[:300]}
    tenta("status", "mercado/status")
    tenta("pontuados", "atletas/pontuados", lambda d: {"chaves": list(d)[:10], "rodada": d.get("rodada"), "n": len(d.get("atletas") or {}),
          "exemplo": list((d.get("atletas") or {}).items())[:2]})
    tenta("partidas", "partidas", lambda d: [{k: p.get(k) for k in ("clube_casa_id", "clube_visitante_id", "partida_data", "status_transmissao_tr", "periodo_tr", "status_cronometro_tr", "placar_oficial_mandante", "placar_oficial_visitante", "valida")} for p in d.get("partidas", [])][:10])
    for tid in (26350318, 300778):
        tenta(f"time_{tid}_atual", f"time/id/{tid}", lambda d: {"chaves": list(d), "pontos": d.get("pontos"), "pontos_campeonato": d.get("pontos_campeonato"), "capitao_id": d.get("capitao_id"),
              "reserva_luxo_id": d.get("reserva_luxo_id"), "rodada_atual": d.get("rodada_atual"), "n_atletas": len(d.get("atletas") or []),
              "atleta0": (d.get("atletas") or [{}])[0], "reservas": [{k: r.get(k) for k in ("atleta_id", "posicao_id", "apelido")} for r in (d.get("reservas") or [])],
              "titulares": [{k: a.get(k) for k in ("atleta_id", "posicao_id", "apelido", "clube_id", "pontos_num")} for a in (d.get("atletas") or [])]})
        tenta(f"time_{tid}_r30", f"time/id/{tid}/30", lambda d: {"pontos": d.get("pontos"), "capitao_id": d.get("capitao_id"), "reserva_luxo_id": d.get("reserva_luxo_id"),
              "titulares": [{k: a.get(k) for k in ("atleta_id", "posicao_id", "pontos_num", "entrou_em_campo")} for a in (d.get("atletas") or [])],
              "reservas": [{k: a.get(k) for k in ("atleta_id", "posicao_id", "pontos_num", "entrou_em_campo")} for a in (d.get("reservas") or [])]})
    open("segunda_fase/sonda_parciais.json", "w").write(json.dumps(out, ensure_ascii=False, indent=1, default=str))
