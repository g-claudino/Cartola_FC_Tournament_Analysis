"""Diagnóstico temporário: testa formatos da API pública da ESPN e salva as respostas."""
import json, requests
base = "https://site.api.espn.com/apis/site/v2/sports/soccer/{liga}/scoreboard"
testes = {
  "lib_sem_param": ("conmebol.libertadores", ""),
  "lib_um_dia": ("conmebol.libertadores", "?dates=20260923"),
  "lib_range7": ("conmebol.libertadores", "?dates=20260915-20260922"),
  "lib_range30_lim100": ("conmebol.libertadores", "?dates=20260901-20260930&limit=100"),
  "lib_range30_lim900": ("conmebol.libertadores", "?dates=20260901-20260930&limit=900"),
  "lib_futuro": ("conmebol.libertadores", "?dates=20261015-20261030"),
  "bra1_range7": ("bra.1", "?dates=20261009-20261014"),
  "copa_range30": ("bra.copa_do_brazil", "?dates=20260901-20260930"),
  "sula_range30": ("conmebol.sudamericana", "?dates=20260901-20260930"),
}
out = {}
for k, (liga, q) in testes.items():
    try:
        r = requests.get(base.format(liga=liga) + q, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        info = {"status": r.status_code}
        try:
            j = r.json(); ev = j.get("events", [])
            info.update(n=len(ev), chaves=list(j)[:8], exemplo=(ev[0]["date"], [c["team"]["displayName"] for c in ev[0]["competitions"][0]["competitors"]]) if ev else None,
                        temporada=j.get("season"), dia=j.get("day"))
        except Exception:
            info["corpo"] = r.text[:300]
    except Exception as e:
        info = {"erro": str(e)[:300]}
    out[k] = info
open("segunda_fase/sonda_espn.json", "w").write(json.dumps(out, ensure_ascii=False, indent=1, default=str))
print(out)
