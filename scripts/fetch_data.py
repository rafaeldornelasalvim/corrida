"""Busca atividades e bem-estar no Intervals.icu e grava data/data.json.
Opcional: se houver credenciais do Strava, completa atividades que o Intervals
recebe do Strava sem detalhes (limitação da API do Strava)."""
import os, json, base64, urllib.request, urllib.parse, datetime as dt

KEY = os.environ["INTERVALS_API_KEY"].strip()
AID = os.environ["INTERVALS_ATHLETE_ID"].strip()
BASE = "https://intervals.icu/api/v1"
AUTH = "Basic " + base64.b64encode(f"API_KEY:{KEY}".encode()).decode()

def get(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)

def icu(path, **q):
    qs = ("?" + urllib.parse.urlencode(q)) if q else ""
    return get(f"{BASE}/athlete/{AID}{path}{qs}", {"Authorization": AUTH})

def norm(a, strava=False):
    local = (a.get("start_date_local") or "")[:16]
    if strava:
        t, d = a.get("moving_time") or 0, a.get("distance") or 0
        typ = a.get("sport_type") or a.get("type") or ""
        ident = "s" + str(a.get("id"))
    else:
        t = a.get("moving_time") or a.get("elapsed_time") or 0
        d = a.get("distance") or 0
        typ = a.get("type") or ""
        ident = str(a.get("id"))
    return dict(
        id=ident, date=local[:10], dt=local, type=typ, name=a.get("name") or "",
        dist=round(d / 1000, 3), time=t, elev=round(a.get("total_elevation_gain") or 0),
        hr=a.get("average_heartrate"), maxhr=a.get("max_heartrate"),
        load=a.get("icu_training_load"), cad=a.get("average_cadence"), stub=not t,
    )

def strava_activities():
    cid, cs, rt = (os.environ.get(k) for k in
                   ("STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET", "STRAVA_REFRESH_TOKEN"))
    if not (cid and cs and rt):
        return []
    body = urllib.parse.urlencode(dict(client_id=cid, client_secret=cs,
            refresh_token=rt, grant_type="refresh_token")).encode()
    with urllib.request.urlopen(urllib.request.Request(
            "https://www.strava.com/oauth/token", data=body), timeout=60) as r:
        tok = json.load(r)["access_token"]
    out, page = [], 1
    while True:
        items = get(f"https://www.strava.com/api/v3/athlete/activities?per_page=200&page={page}",
                    {"Authorization": "Bearer " + tok})
        if not items:
            break
        out += items
        page += 1
    return out

today = dt.date.today().isoformat()
acts = {}
for a in icu("/activities", oldest="2000-01-01", newest=today):
    n = norm(a)
    if n["dt"]:
        acts[n["dt"]] = n

try:
    for s in strava_activities():
        n = norm(s, strava=True)
        if n["dt"] and (n["dt"] not in acts or acts[n["dt"]]["stub"]):
            acts[n["dt"]] = n
except Exception as e:
    print("Aviso: Strava ignorado ->", e)

wellness = []
try:
    for w in icu("/wellness", oldest="2010-01-01", newest=today):
        if w.get("ctl") is None and w.get("atl") is None:
            continue
        wellness.append(dict(
            date=w.get("id"),
            ctl=round(w["ctl"], 1) if w.get("ctl") is not None else None,
            atl=round(w["atl"], 1) if w.get("atl") is not None else None,
            rhr=w.get("restingHR"), hrv=w.get("hrv"), weight=w.get("weight")))
except Exception as e:
    print("Aviso: wellness ignorado ->", e)

name = ""
try:
    name = icu("").get("name") or ""
except Exception:
    pass

lst = sorted(acts.values(), key=lambda x: x["dt"])
out = dict(updated=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           athlete=name, stubs=sum(1 for x in lst if x["stub"]),
           activities=[x for x in lst if not x["stub"]], wellness=wellness)
# 'updated' só muda se os dados mudarem, evitando commits inúteis
try:
    old = json.load(open("data/data.json"))
    if {**old, "updated": None} == {**out, "updated": None}:
        out["updated"] = old.get("updated")
except Exception:
    pass
os.makedirs("data", exist_ok=True)
json.dump(out, open("data/data.json", "w"), ensure_ascii=False, separators=(",", ":"))
print(f"{len(out['activities'])} atividades, {out['stubs']} sem detalhes, {len(wellness)} dias de bem-estar")
