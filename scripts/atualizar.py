"""Atualiza dados.json com os resultados das midterms 2026 publicados pela NBC News.

Lê os dados estruturados (__NEXT_DATA__) das páginas de resultados da Câmara e do
Senado. Se algo não fechar (estados faltando, somas diferentes do total nacional,
página fora do formato esperado), o script para com erro e NÃO altera dados.json,
para o site nunca mostrar números quebrados.

Uso: python3 scripts/atualizar.py [caminho/para/dados.json]
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

HOUSE_URL = "https://www.nbcnews.com/politics/2026-elections/house-results"
SENATE_URL = "https://www.nbcnews.com/politics/2026-elections/senate-results"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
STATES = set("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO "
             "MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split())


class DadosInvalidos(Exception):
    pass


def page_props(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=60) as r:
        html = r.read().decode("utf-8", "replace")
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        raise DadosInvalidos(f"{url}: bloco __NEXT_DATA__ não encontrado")
    return json.loads(m.group(1))["props"]["pageProps"]


def to_iso(last_modified):
    try:
        return parsedate_to_datetime(last_modified).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ler_camara():
    p = page_props(HOUSE_URL)
    t = p["tableData"]
    nat = t["seatsByParty"]
    D, R, u = int(nat["dem"]), int(nat["rep"]), int(nat["uncalled"])
    if D + R + u != 435:
        raise DadosInvalidos(f"Câmara: {D}+{R}+{u} != 435")
    states = {}
    for s in t["states"]:
        ab = s["stateAbbr"]
        d, r, un, tot = int(s["dem"]["seatsWon"]), int(s["rep"]["seatsWon"]), int(s["uncalledRaces"]), int(s["totalSeats"])
        if d + r + un != tot:
            raise DadosInvalidos(f"Câmara {ab}: {d}+{r}+{un} != {tot}")
        states[ab] = {"D": d, "R": r, "u": un}
    if set(states) != STATES:
        raise DadosInvalidos(f"Câmara: estados diferentes do esperado: {sorted(set(states) ^ STATES)}")
    sd = sum(v["D"] for v in states.values())
    sr = sum(v["R"] for v in states.values())
    su = sum(v["u"] for v in states.values())
    # Cadeiras de outros partidos podem não aparecer como D/R; só aceite diferença zero.
    if (sd, sr, su) != (D, R, u):
        raise DadosInvalidos(f"Câmara: soma dos estados {sd}/{sr}/{su} != total {D}/{R}/{u}")
    return {"D": D, "R": R, "uncalled": u}, states, p.get("lastModified")


def ler_senado():
    p = page_props(SENATE_URL)
    bar = p["bopData"]["bar"]
    D = int(bar["dem"]["total"]) + int((bar.get("ind") or {}).get("total") or 0)
    R = int(bar["rep"]["total"])
    if not (0 <= D + R <= 100):
        raise DadosInvalidos(f"Senado: {D}+{R} fora de 0..100")
    return {"D": D, "R": R, "uncalled": 100 - D - R}, p.get("lastModified")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "dados.json"
    try:
        old = json.load(open(path, encoding="utf-8"))
    except FileNotFoundError:
        old = {}
    house, states, lm_h = ler_camara()
    senate, lm_s = ler_senado()
    stamps = [x for x in (lm_h, lm_s) if x]
    updated = max((to_iso(x) for x in stamps), default=to_iso(""))

    all_called = house["uncalled"] == 0 and senate["uncalled"] == 0
    new = {
        "updatedAt": updated,
        "source": HOUSE_URL,
        "sourceName": "NBC News",
        "house": house,
        "senate": senate,
        "states": states,
    }
    if not all_called:
        new["note"] = "Resultados parciais; atualiza a cada 30 minutos"

    if {k: v for k, v in new.items() if k != "updatedAt"} == {k: v for k, v in old.items() if k != "updatedAt"} \
            and old.get("updatedAt") == new["updatedAt"]:
        print("Sem mudanças.")
        return
    with open(path, "w", encoding="utf-8") as f:
        json.dump(new, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"Atualizado: Câmara D{house['D']} R{house['R']} ({house['uncalled']} em aberto) | "
          f"Senado D{senate['D']} R{senate['R']} ({senate['uncalled']} em aberto) | {updated}")


if __name__ == "__main__":
    try:
        main()
    except DadosInvalidos as e:
        print(f"ERRO: dados inválidos, dados.json não foi alterado. {e}", file=sys.stderr)
        sys.exit(1)
