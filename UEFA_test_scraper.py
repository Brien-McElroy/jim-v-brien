"""STANDALONE TEST, version 3. Touches nothing else in the repo.

Version 2 listened to what uefa.com asks the network for, and caught the
real feed:

  https://match.uefa.com/v5/matches?competitionId=1&seasonYear=2027
      &fromDate=YYYY-MM-DD&toDate=YYYY-MM-DD
      &phase=ALL&limit=50&offset=0&order=ASC&utcOffset=0

It is addressed BY DATE, not by matchday number - which is why every URL
I guessed in version 1 came back 404. We already know each matchday's
dates from UEFA_fixtures.json, so that is all we need.

No browser now. Just one request per date, so this runs in seconds.

It still marks its own homework against Matchday 3, whose scores we know.
It never fails the run and never emails anybody.

    python UEFA_test_scraper.py          # Matchday 3 (known answers)
    python UEFA_test_scraper.py 4        # Matchday 4 for real
"""
import json, os, re, sys, unicodedata, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
FEED = ("https://match.uefa.com/v5/matches"
        "?competitionId=1&seasonYear=2027&phase=ALL"
        "&fromDate={d}&toDate={d}&limit=50&offset=0&order=ASC&utcOffset=0")

KNOWN_MD3 = [
    ("Fenerbahce", "Slavia Praha", 2, 2), ("Sabah", "B. Dortmund", 1, 2),
    ("Paris", "Barcelona", 4, 2), ("Liverpool", "Villarreal", 4, 3),
    ("Man City", "AEK Athens", 5, 1), ("Roma", "S. Bratislava", 4, 0),
    ("Porto", "PSV", 0, 1), ("Napoli", "Bodo/Glimt", 4, 3),
    ("Stuttgart", "Atleti", 1, 1), ("Lille", "Galatasaray", 2, 4),
    ("Como", "Man Utd", 4, 1), ("Bayern Munchen", "Arsenal", 2, 2),
    ("Real Madrid", "Leipzig", 4, 1), ("Inter", "Shakhtar", 1, 0),
    ("Sporting CP", "LASK", 2, 3), ("Aston Villa", "Viking", 3, 1),
    ("Club Brugge", "Lens", 3, 0), ("Real Betis", "Feyenoord", 1, 0),
]

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


# --------------------------------------------------- pulling a match apart
NAME_KEYS = ["internationalName", "displayName", "displayOfficialName",
             "teamName", "officialName", "mediumName", "shortName", "name"]


def side_name(side):
    """Find the club's name inside a homeTeam/awayTeam object, whatever
    UEFA chose to call the field."""
    if not isinstance(side, dict):
        return None
    for k in NAME_KEYS:
        v = side.get(k)
        if isinstance(v, str) and v.strip():
            return v
    # last resort: any key with 'name' in it holding a plain string
    for k, v in side.items():
        if "name" in k.lower() and isinstance(v, str) and v.strip():
            return v
    tr = side.get("translations") or {}
    if isinstance(tr, dict):
        for v in tr.values():
            if isinstance(v, dict):
                en = v.get("EN") or v.get("en")
                if isinstance(en, str) and en.strip():
                    return en
    return None


def goals(m):
    """Find the full-time goals, whatever shape the score is in."""
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
    for sidekey, which in (("homeTeam", 0), ("awayTeam", 1)):
        pass
    return None, None


def finished(m):
    s = str(m.get("status") or m.get("matchStatus") or "").upper()
    return s in ("FINISHED", "FULL_TIME", "PLAYED", "COMPLETED", "FT") or s == ""


def read_date(d, log, dump=False):
    url = FEED.format(d=d)
    log("  GET %s" % url)
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Referer": "https://www.uefa.com/",
        "Origin": "https://www.uefa.com",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        log("    -> HTTP %s" % e.code)
        return []
    except Exception as e:
        log("    -> %s" % e)
        return []
    try:
        data = json.loads(raw)
    except Exception:
        log("    -> not JSON: %s" % raw[:200])
        return []
    items = data if isinstance(data, list) else (data.get("data") or data.get("matches") or [])
    log("    -> %d matches listed" % len(items))
    if dump and items:
        log("    the first match looks like this (field names matter):")
        log(json.dumps(items[0], indent=2, ensure_ascii=False)[:2600])
    out = []
    for m in items:
        if not isinstance(m, dict):
            continue
        hn, an = side_name(m.get("homeTeam")), side_name(m.get("awayTeam"))
        hg, ag = goals(m)
        H, A = team(hn), team(an)
        if not H or not A:
            if hn or an:
                log("    ?? could not place %r / %r" % (hn, an))
            continue
        if hg is None or ag is None:
            log("    -- %s v %s has no score yet (status %r)"
                % (H, A, m.get("status") or m.get("matchStatus")))
            continue
        out.append((H, A, int(hg), int(ag)))
    return out


# ---------------------------------------------------------------- the test
def main():
    md = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    checking = (md == 3)
    print("=" * 66)
    print("UEFA scraper test v3 - Matchday %d%s" % (md, "  (answers known)" if checking else ""))
    print("=" * 66)
    log = lambda s: print(s)

    # Which dates does this matchday run on? Straight from our own fixture list.
    try:
        with open(os.path.join(HERE, "UEFA_fixtures.json"), encoding="utf-8") as f:
            fx = json.load(f)
        rows = (fx["played"] if str(md) in fx.get("played", {}) else fx["future"])[str(md)]
        dates = sorted({r[0] for r in rows})
    except Exception as e:
        print("Could not read UEFA_fixtures.json (%s)." % e)
        print("Make sure UEFA_fixtures.json is in the repo next to this script.")
        return
    print("\nMatchday %d was played on: %s" % (md, ", ".join(dates)))

    got = []
    for i, d in enumerate(dates):
        got += read_date(d, log, dump=(i == 0))

    print("\n" + "=" * 66)
    if not got:
        print("VERDICT: the feed gave nothing back.")
        print("Copy the whole log into the chat.")
        return
    for h, a, hg, ag in got:
        print("  %-16s %d - %d  %s" % (h, hg, ag, a))
    print("\n%d matches read." % len(got))

    if len(got) != 18:
        print("\nVERDICT: expected 18, got %d. Not safe to use yet." % len(got))
        print("Copy the whole log into the chat.")
        return
    if not checking:
        print("\nVERDICT: read all 18. Spot-check a couple against uefa.com.")
        return

    want = {(h, a): (hg, ag) for h, a, hg, ag in KNOWN_MD3}
    bad = []
    for h, a, hg, ag in got:
        if (h, a) not in want:
            bad.append("%s v %s is not a Matchday 3 fixture" % (h, a))
        elif want[(h, a)] != (hg, ag):
            bad.append("%s v %s: read %d-%d, should be %d-%d" % (h, a, hg, ag, *want[(h, a)]))
    print()
    if bad:
        print("VERDICT: FAILED. %d problem(s):" % len(bad))
        for x in bad:
            print("  - " + x)
        print("Copy the whole log into the chat.")
    else:
        print("VERDICT: PASSED. All 18 matches read correctly, straight from UEFA.")
        print("Tell me and I will wire it into the weekly job.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        print("The test itself crashed: %s" % e)
        traceback.print_exc()
    sys.exit(0)  # never turn the run red
