"""Build site/index.html (Jim's read-only results page) from history.json (weeks 1-5)
plus every saved tables/*.csv. Same page as Brien's Claude page, minus the editing tabs."""
import csv, glob, json, os, re, sys

NAME2ID = {"Arsenal": "ars", "Aston Villa": "avl", "Bournemouth": "bou", "Brentford": "bre",
           "Brighton & Hove Albion": "bha", "Chelsea": "che", "Coventry City": "cov",
           "Crystal Palace": "cry", "Everton": "eve", "Fulham": "ful", "Hull City": "hul",
           "Ipswich Town": "ips", "Leeds United": "lee", "Liverpool": "liv",
           "Manchester City": "mci", "Manchester United": "mun", "Newcastle United": "new",
           "Nottingham Forest": "nfo", "Sunderland": "sun", "Tottenham Hotspur": "tot"}


def week_obj(n, table, date):
    names = [t for t, _ in table]
    pts = [p for _, p in table]
    if sorted(names) != sorted(NAME2ID) or pts != sorted(pts, reverse=True):
        raise ValueError("Week %d table is not a valid 20-team table" % n)
    return {"id": "b%d" % n, "label": "Week %d" % n, "date": date, "ts": n, "baked": True,
            "order": [NAME2ID[t] for t in names], "pts": {NAME2ID[t]: p for t, p in table}}


weeks = {}
for h in json.load(open("history.json")):
    weeks[h["week"]] = week_obj(h["week"], h["table"], "")
dated = {}
for fn in sorted(glob.glob("tables/*.csv")):
    m = re.search(r"(\d{4}-\d{2}-\d{2})", fn)
    fdate = m.group(1) if m else ""
    rows = list(csv.DictReader(open(fn, encoding="utf-8")))
    n = int(rows[0]["played"])
    if n not in dated or fdate >= dated[n][0]:
        dated[n] = (fdate, [(r["team"], int(r["points"])) for r in rows])
for n, (d, table) in dated.items():
    weeks[n] = week_obj(n, table, d)
nums = sorted(weeks)
if nums != list(range(1, nums[-1] + 1)):
    sys.exit("Missing weeks, have %s" % nums)
allw = [weeks[n] for n in nums]
final = {"done": nums[-1] >= 38, "champPts": allw[-1]["pts"][allw[-1]["order"][0]] if nums[-1] >= 38 else None}

tpl = open("site_template.html", encoding="utf-8").read()
tpl, k = re.subn(r"var BAKED=\[.*?\];\nvar PICKS", lambda m: "var BAKED=" + json.dumps(allw, separators=(",", ":")) + ";\nvar PICKS", tpl, count=1, flags=re.S)
if k != 1:
    sys.exit("Template marker not found")
head = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="robots" content="noindex,nofollow"></head><body>'
        '<script>window.STATIC_MODE=true;window.STATIC_FINAL=%s;</script>' % json.dumps(final))
os.makedirs("site", exist_ok=True)
open("site/index.html", "w", encoding="utf-8").write(head + tpl + "</body></html>")
print("Built site/index.html with weeks", nums[0], "to", nums[-1])
