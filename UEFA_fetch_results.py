"""Read a finished Champions League matchday from UEFA and store the scores.

Runs every day. Does nothing at all unless the next unscored matchday is
complete - all 18 matches played - so a run during a matchday finishes
quietly rather than turning the job red.

Reads   UEFA_fixtures.json   (which dates each matchday is played on)
        UEFA_state.json      (picks, and the matchdays already stored)
Writes  UEFA_state.json      (with the new matchday's 18 scores)

Exit code is always 0 unless something is genuinely wrong, so a matchday
still in progress never sends a failure email.
"""
import datetime, json, os, re, sys, unicodedata, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "UEFA_state.json")
FIXTURES = os.path.join(HERE, "UEFA_fixtures.json")
FEED = ("https://match.uefa.com/v5/matches"
        "?competitionId=1&seasonYear=2027&phase=ALL"
        "&fromDate={d}&toDate={d}&limit=50&offset=0&order=ASC&utcOffset=0")
MDS = [4, 5, 6, 7, 8]

ALIASES = {
    "Arsenal": ["arsenal"],
    "Aston Villa": ["aston villa", "villa"],
    "AEK Athens": ["aek athens", "aek"],
    "Atleti": ["atleti", "atletico madrid", "atletico de madrid", "club atletico de madrid"],
    "Barcelona": ["barcelona", "fc barcelona"],
    "Bayern Munchen": ["bayern munchen", "bayern munich", "fc bayern munchen", "bayern"],
    "B. Dortmund": ["b dortmund", "borussia dortmund", "dortmund", "bvb"],
    "Bodo/Glimt": ["bodo glimt", "bodoglimt", "fk bodo glimt"],
    "Club Brugge": ["club brugge", "brugge", "club brugge kv"],
    "Como": ["como", "como 1907"],
    "Fenerbahce": ["fenerbahce", "fenerbahce sk"],
    "Feyenoord": ["feyenoord"],
    "Galatasaray": ["galatasaray", "galatasaray as"],
    "Inter": ["inter", "internazionale", "fc internazionale milano", "inter milan"],
    "LASK": ["lask", "lask linz"],
    "Leipzig": ["leipzig", "rb leipzig"],
    "Lens": ["lens", "rc lens"],
    "Lille": ["lille", "losc lille", "losc"],
    "Liverpool": ["liverpool"],
    "Man City": ["man city", "manchester city"],
    "Man Utd": ["man utd", "man united", "manchester united"],
    "Napoli": ["napoli", "ssc napoli"],
    "Paris": ["paris", "paris saint germain", "psg", "paris sg"],
    "Porto": ["porto", "fc porto"],
    "PSV": ["psv", "psv eindhoven"],
    "Real Betis": ["real betis", "betis", "real betis balompie"],
    "Real Madrid": ["real madrid"],
    "Roma": ["roma", "as roma"],
    "Sabah": ["sabah", "sabah fk"],
    "Shakhtar": ["shakhtar", "shakhtar donetsk"],
    "Slavia Praha": ["slavia praha", "slavia prague", "sk slavia praha"],
    "Sporting CP": ["sporting cp", "sporting", "sporting lisbon", "sporting clube de portugal"],
    "S. Bratislava": ["s bratislava", "slovan bratislava", "sk slovan bratislava", "slovan"],
    "Stuttgart": ["stuttgart", "vfb stuttgart"],
    "Villarreal": ["villarreal", "villarreal cf"],
    "Viking": ["viking", "viking fk"],
}
NOISE = {"fc", "cf", "ac", "as", "sk", "fk", "kv", "sc", "ss", "ssc", "rb", "rc",
         "vfb", "losc", "bk", "if", "cp", "club", "de", "1907"}
LETTERS = {"ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE",
           "ß": "ss", "đ": "d", "Đ": "D", "ł": "l",
           "Ł": "L", "þ": "th", "ı": "i"}


class NotReady(Exception):
    """The matchday has not finished yet. Normal; finish quietly."""


def norm(s):
    s = "".join(LETTERS.get(c, c) for c in str(s))
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return re.sub(r"\s+", " ", s)


LOOKUP = {}
for canon, names in ALIASES.items():
    LOOKUP[norm(canon)] = canon
    for n in names:
        LOOKUP[norm(n)] = canon


def team(raw):
    k = norm(raw)
    if not k:
        return None
    if k in LOOKUP:
        return LOOKUP[k]
    core = " ".join(w for w in k.split() if w not in NOISE)
    if core in LOOKUP:
        return LOOKUP[core]
    best, score = None, 0
    for alias, canon in LOOKUP.items():
        a = set(w for w in alias.split() if w not in NOISE)
        b = set(core.split())
        if not a or not b:
            continue
        ov = len(a & b)
        if ov and ov > score and (a <= b or b <= a):
            best, score = canon, ov
    return best


NAME_KEYS = ["internationalName", "displayName", "displayOfficialName",
             "teamName", "officialName", "mediumName", "shortName", "name"]


def side_name(side):
    if not isinstance(side, dict):
        return None
    for k in NAME_KEYS:
        v = side.get(k)
        if isinstance(v, str) and v.strip():
            return v
    tr = side.get("translations") or {}
    if isinstance(tr, dict):
        for key in ("displayName", "shortName", "displayOfficialName"):
            v = tr.get(key)
            if isinstance(v, dict):
                en = v.get("EN")
                if isinstance(en, str) and en.strip():
                    return en
    return None


def goals(m):
    sc = m.get("score")
    if isinstance(sc, dict):
        for key in ("total", "regular", "normal", "fullTime"):
            t = sc.get(key)
            if isinstance(t, dict) and t.get("home") is not None and t.get("away") is not None:
                return t["home"], t["away"]
        if sc.get("home") is not None and sc.get("away") is not None:
            return sc["home"], sc["away"]
    for a, b in (("homeScore", "awayScore"), ("homeGoals", "awayGoals")):
        if m.get(a) is not None and m.get(b) is not None:
            return m[a], m[b]
    return None, None


def read_date(d):
    url = FEED.format(d=d)
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Referer": "https://www.uefa.com/",
    })
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read().decode("utf-8", "replace")
            data = json.loads(raw)
            items = data if isinstance(data, list) else (data.get("data") or data.get("matches") or [])
            out = {}
            for m in items:
                if not isinstance(m, dict):
                    continue
                H, A = team(side_name(m.get("homeTeam"))), team(side_name(m.get("awayTeam")))
                if not H or not A:
                    continue
                hg, ag = goals(m)
                out[(H, A)] = None if hg is None or ag is None else (int(hg), int(ag))
            return out
        except Exception as e:
            last = e
            if attempt < 2:
                import time
                time.sleep(8)
    raise RuntimeError("could not read %s: %s" % (d, last))


def load_json(path, fallback=None):
    if not os.path.exists(path):
        return fallback
    with open(path, encoding="utf-8") as f:
        txt = f.read().strip()
    return json.loads(txt) if txt else fallback


def main():
    fx = load_json(FIXTURES)
    if not fx:
        print("FAILED: UEFA_fixtures.json is missing.")
        return 1
    state = load_json(STATE, {}) or {}
    state.setdefault("picks", {"brien": {}, "jim": {}})
    state.setdefault("results", {})
    state.setdefault("bracket", {"setup": {}, "picks": {"brien": {}, "jim": {}}, "winners": {}})

    todo = [md for md in MDS if ("md%d" % md) not in state["results"]]
    if not todo:
        print("All eight matchdays are already stored. Nothing to do.")
        return 0
    md = todo[0]
    rows = fx["future"][str(md)]
    dates = sorted({r[0] for r in rows})
    today = datetime.date.today().isoformat()
    if today < dates[-1]:
        print("Matchday %d runs %s. Not finished yet, nothing to do."
              % (md, " and ".join(dates)))
        return 0

    print("Looking for Matchday %d (%s)." % (md, " and ".join(dates)))
    seen = {}
    for d in dates:
        seen.update(read_date(d))

    scores, missing = [], []
    for dt, h, a in rows:
        got = seen.get((h, a))
        if got is None:
            missing.append("%s v %s" % (h, a))
            scores.append(None)
        else:
            scores.append([got[0], got[1]])
    if missing:
        print("Matchday %d is not complete yet - %d match(es) with no final score:"
              % (md, len(missing)))
        for x in missing[:6]:
            print("   " + x)
        print("Nothing to do. Will look again tomorrow.")
        return 0

    state["results"]["md%d" % md] = {"s": scores, "at": today}
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, separators=(",", ":"))
    print("Stored Matchday %d:" % md)
    for (dt, h, a), s in zip(rows, scores):
        print("  %-16s %d - %d  %s" % (h, s[0], s[1], a))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("FAILED:", e)
        sys.exit(1)
