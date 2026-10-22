"""STANDALONE TEST. Touches nothing else in the repo.

Tries to read Champions League results off uefa.com and then marks its own
homework: it fetches a matchday we already know the answers to (Matchday 3,
played 20-21 October 2026) and compares what it read against the real scores.

Run it from the Actions tab. It never fails the run and never emails anybody,
so the worst that happens is a green run that says it did not work.

    python UEFA_test_scraper.py          # checks Matchday 3 (known answers)
    python UEFA_test_scraper.py 4        # tries Matchday 4 for real
"""
import json, os, re, sys, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))

# The 20-21 October results, straight off the UEFA site. The scraper has to
# reproduce these exactly or it is not trustworthy.
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

# How the 36 clubs may be written on UEFA's own pages.
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


# Letters that are not accents but whole characters, so stripping accents
# alone turns Bodo/Glimt into "bod glimt" and the club is never found.
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
    """Map whatever UEFA calls a club onto our name, or None."""
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


# ---------------------------------------------------------------- strategies
def try_json_api(md, log):
    """UEFA's own match feed. Cheapest and most stable if it answers."""
    try:
        import urllib.request
    except Exception as e:
        log("  urllib unavailable: %s" % e)
        return None
    bases = [
        "https://match.uefa.com/v5/matches?competitionId=1&seasonYear=2027&matchDayNumber=%d&limit=60" % md,
        "https://match.uefa.com/v5/matches?competitionId=1&seasonYear=2027&roundNumber=%d&limit=60" % md,
        "https://match.uefa.com/v2/matches?competitionId=1&seasonYear=2027&matchDayNumber=%d&limit=60" % md,
    ]
    for url in bases:
        log("  GET %s" % url)
        try:
            req = urllib.request.Request(url, headers={
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (compatible; jim-v-brien/1.0)",
            })
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read().decode("utf-8", "replace")
        except Exception as e:
            log("    -> %s" % e)
            continue
        if not raw.strip():
            log("    -> empty response")
            continue
        try:
            data = json.loads(raw)
        except Exception:
            log("    -> not JSON (first 200 chars): %s" % raw[:200].replace("\n", " "))
            continue
        items = data if isinstance(data, list) else (data.get("matches") or data.get("data") or [])
        log("    -> %d items" % len(items))
        out = []
        for m in items:
            try:
                h = (m.get("homeTeam") or {})
                a = (m.get("awayTeam") or {})
                hn = h.get("internationalName") or h.get("displayName") or h.get("teamName") or h.get("name")
                an = a.get("internationalName") or a.get("displayName") or a.get("teamName") or a.get("name")
                sc = (m.get("score") or {}).get("total") or {}
                hg, ag = sc.get("home"), sc.get("away")
                if hg is None or ag is None:
                    continue
                H, A = team(hn), team(an)
                if not H or not A:
                    log("    ?? could not place %r / %r" % (hn, an))
                    continue
                out.append((H, A, int(hg), int(ag)))
            except Exception:
                continue
        if out:
            return out
    return None


def try_browser(md, log):
    """Fall back to reading the public fixtures page with a headless browser."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        log("  playwright not installed: %s" % e)
        return None
    urls = ["https://www.uefa.com/uefachampionsleague/fixtures-results/",
            "https://www.uefa.com/uefachampionsleague/standings/"]
    for url in urls:
        log("  OPEN %s" % url)
        try:
            with sync_playwright() as p:
                b = p.chromium.launch()
                try:
                    pg = b.new_page(viewport={"width": 1400, "height": 3000})
                    pg.goto(url, wait_until="domcontentloaded", timeout=60000)
                    for sel in ("#onetrust-reject-all-handler", "#onetrust-accept-btn-handler",
                                "button:has-text('Reject')", "button:has-text('Accept')"):
                        try:
                            pg.click(sel, timeout=2500)
                            break
                        except Exception:
                            pass
                    pg.wait_for_timeout(6000)
                    for _ in range(12):
                        pg.mouse.wheel(0, 2400)
                        pg.wait_for_timeout(700)
                    txt = pg.inner_text("body")
                finally:
                    b.close()
        except Exception as e:
            log("    -> %s" % e)
            continue
        log("    -> read %d characters of page text" % len(txt))
        out = parse_text(txt, md, log)
        if out:
            return out
        head = " | ".join(l.strip() for l in txt.splitlines() if l.strip())[:400]
        log("    -> nothing parsed. Page began: %s" % head)
    return None


def parse_text(txt, md, log):
    """Pull 'Team 2 Team 1' style blocks out of the visible page text."""
    lines = [l.strip() for l in txt.splitlines() if l.strip()]
    want = None
    for i, l in enumerate(lines):
        if re.search(r"matchday\s*%d\b" % md, l, re.I):
            want = i
            break
    if want is None:
        log("    -> no 'Matchday %d' heading in the page text" % md)
        return None
    out, i = [], want
    stop = re.compile(r"matchday\s*(?!%d\b)\d+" % md, re.I)
    while i < len(lines) and len(out) < 18:
        if i > want and stop.search(lines[i]):
            break
        t1 = team(lines[i])
        if t1 and i + 3 < len(lines):
            g1, t2, g2 = lines[i + 1], team(lines[i + 2]), lines[i + 3]
            if t2 and re.fullmatch(r"\d{1,2}", g1) and re.fullmatch(r"\d{1,2}", g2):
                out.append((t1, t2, int(g1), int(g2)))
                i += 4
                continue
        i += 1
    return out or None


# ---------------------------------------------------------------- the test
def main():
    md = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    checking = (md == 3)
    print("=" * 62)
    print("UEFA scraper test - Matchday %d%s" % (md, "  (answers known)" if checking else ""))
    print("=" * 62)

    log = lambda s: print(s)
    got = None
    for name, fn in (("UEFA JSON feed", try_json_api), ("headless browser", try_browser)):
        print("\n-- trying the %s" % name)
        try:
            got = fn(md, log)
        except Exception as e:
            log("  blew up: %s" % e)
            got = None
        if got:
            print("  got %d matches this way." % len(got))
            break
        print("  no luck.")

    print("\n" + "=" * 62)
    if not got:
        print("VERDICT: could not read the results. Enter them by hand in the page.")
        print("Copy this whole log into the chat and I will work from it.")
        return
    for h, a, hg, ag in got:
        print("  %-16s %d - %d  %s" % (h, hg, ag, a))
    if len(got) != 18:
        print("\nVERDICT: only %d of 18 matches. Not safe to use yet." % len(got))
        return
    if not checking:
        print("\nVERDICT: read all 18. Check a couple against uefa.com before trusting it.")
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
        print("Copy this whole log into the chat and I will fix it.")
    else:
        print("VERDICT: PASSED. All 18 matches read correctly.")
        print("The scraper works. Tell me and I will wire it into the weekly job.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("The test itself crashed: %s" % e)
    sys.exit(0)  # never turn the run red
