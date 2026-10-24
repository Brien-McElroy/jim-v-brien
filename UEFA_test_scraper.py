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
    python UEFA_test_scraper.py clubs    # what UEFA holds about each club
    python UEFA_test_scraper.py players  # top scorers, and the club trivia
                                         #   the clubs probe could not find
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


# ------------------------------------------------- what does UEFA hold on each club?
TEAMS_URL = ("https://comp.uefa.com/v2/teams"
             "?competitionId=1&seasonYear=2027&phase=ALL&limit=50&offset=0")

# The things we would like to show in the comparison box, and the field names
# UEFA might plausibly use for each.
WANTED = {
    "full name":   ["displayOfficialName", "officialName", "internationalName", "displayName"],
    "short name":  ["internationalName", "displayName", "mediumName", "shortName"],
    "nickname":    ["nickname", "nickName", "alias", "shortClubName"],
    "home town":   ["city", "cityName", "town", "venueCity", "homeCity"],
    "founded":     ["founded", "foundationDate", "foundedYear", "yearFounded", "established"],
    "stadium":     ["venue", "venueName", "stadium", "stadiumName", "homeVenue"],
    "country":     ["countryCode", "country", "associationId"],
    "club id":     ["id", "teamId"],
}


def flatten(o, prefix=""):
    """Every field in the record, including nested ones, as path -> value."""
    out = {}
    if isinstance(o, dict):
        for k, v in o.items():
            p = (prefix + "." + k) if prefix else k
            if isinstance(v, (dict, list)):
                out.update(flatten(v, p))
            else:
                out[p] = v
    elif isinstance(o, list):
        for i, v in enumerate(o[:3]):
            out.update(flatten(v, prefix + "[%d]" % i))
    return out


def probe_clubs(log):
    log("=" * 66)
    log("What UEFA holds about each club")
    log("=" * 66)
    log("")
    log("  GET " + TEAMS_URL)
    req = urllib.request.Request(TEAMS_URL, headers={
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Referer": "https://www.uefa.com/",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8", "replace")
    except Exception as e:
        log("    -> %s" % e)
        log("")
        log("VERDICT: could not reach the club feed. Copy this log into the chat.")
        return
    try:
        data = json.loads(raw)
    except Exception:
        log("    -> not JSON. First 300 characters: " + raw[:300])
        return
    teams = data if isinstance(data, list) else (data.get("data") or data.get("teams") or [])
    log("    -> %d clubs listed" % len(teams))
    if not teams:
        log("VERDICT: the feed answered but listed no clubs. Copy this log into the chat.")
        return

    log("")
    log("-- every field on the first club, so nothing is guessed --")
    flat = flatten(teams[0])
    for k in sorted(flat):
        v = str(flat[k])
        if len(v) > 90:
            v = v[:90] + "..."
        log("   %-46s %s" % (k, v))

    log("")
    log("-- is what we want actually there? (across all %d clubs) --" % len(teams))
    for label, keys in WANTED.items():
        found = None
        for t in teams:
            f = flatten(t)
            for key in keys:
                hits = [k for k in f if k.split(".")[-1].lower() == key.lower() and f[k] not in (None, "")]
                if hits:
                    found = hits[0]
                    break
            if found:
                break
        if found:
            have = sum(1 for t in teams if flatten(t).get(found) not in (None, ""))
            ex = str(flatten(teams[0]).get(found, ""))[:40]
            log("   %-11s YES  as '%s'  (%d of %d clubs)   e.g. %s"
                % (label, found, have, len(teams), ex))
        else:
            log("   %-11s no   not under any of: %s" % (label, ", ".join(keys)))

    log("")
    log("-- the club ids, which is what the comparison link needs --")
    names = []
    for t in teams:
        f = flatten(t)
        nm = f.get("internationalName") or f.get("displayName") or "?"
        names.append("%s=%s" % (nm, f.get("id", "?")))
    for i in range(0, len(names), 3):
        log("   " + "   ".join("%-26s" % n for n in names[i:i + 3]))

    log("")
    log("=" * 66)
    log("VERDICT: read %d clubs. Copy this whole log into the chat and I will" % len(teams))
    log("build the comparison box from exactly what is above - nothing invented.")


SCORER_PAGE = "https://www.uefa.com/uefachampionsleague/top-scorer/"


def get(url, log, label):
    req = urllib.request.Request(url, headers={
        "Accept": "*/*",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Referer": "https://www.uefa.com/",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", "replace")
    except Exception as e:
        log("    -> %s  (%s)" % (e, label))
        return None


def probe_scorers(log):
    """The top-scorer page is drawn by JavaScript, so the numbers are not in the
    HTML. But the HTML usually still names the address the data comes from -
    and that is the part we need. No browser required."""
    log("")
    log("=" * 66)
    log("Where the top-scorer numbers come from")
    log("=" * 66)
    log("")
    log("  GET " + SCORER_PAGE)
    html = get(SCORER_PAGE, log, "the top-scorer page")
    if not html:
        log("VERDICT: could not open the page. Copy this log into the chat.")
        return
    log("    -> %d characters of HTML" % len(html))

    # any uefa.com address in the page that looks like a data feed
    urls = set(re.findall(r'https?://[a-zA-Z0-9.\-]*uefa\.com/[^"\'\\\s<>)]+', html))
    datay = sorted(u for u in urls if re.search(
        r'(/v\d|api|stat|player|scorer|top|rank|comp\.|match)', u, re.I)
        and not re.search(r'\.(png|jpg|jpeg|svg|gif|webp|css|woff2?|ico)(\?|$)', u, re.I))
    log("")
    log("-- uefa.com addresses in the page that look like data feeds (%d) --" % len(datay))
    for u in datay[:40]:
        log("   " + u[:150])
    if not datay:
        log("   none found that way.")

    # some sites park the whole first page of data in the HTML
    log("")
    log("-- is the data parked in the page itself? --")
    for marker in ("__NEXT_DATA__", "__NUXT__", "window.__INITIAL_STATE__", "application/ld+json"):
        if marker in html:
            i = html.find(marker)
            log("   FOUND %s at character %d" % (marker, i))
            chunk = html[i:i + 1200]
            log("   " + re.sub(r"\s+", " ", chunk)[:600])
        else:
            log("   %s - not present" % marker)

    # names of our clubs appearing in the HTML would mean real content is there
    hits = [t for t in ALIASES if re.search(re.escape(t.split()[0]), html, re.I)]
    log("")
    log("   %d of 36 club names appear in the HTML (a high number means the" % len(hits))
    log("   page carries real content, not just an empty shell)")
    log("")
    log("VERDICT: copy this whole log into the chat. The addresses above tell me")
    log("whether top scorers can be had safely, or whether we leave them out.")


# ------------------------------------------------- probe 2: players, and the
# club details the first probe could not find (home town, founded, stadium)

# Addresses worth trying. None of these is confirmed - that is the whole
# point of the probe. Anything that answers gets its fields listed in full
# so nothing has to be guessed afterwards.
PLAYER_URLS = [
    ("player ranking, goals",
     "https://matchstats.uefa.com/v1/player-ranking?competitionId=1&seasonYear=2027"
     "&phase=ALL&limit=10&offset=0&stats=goals&order=DESC&optionalFields=PLAYER,TEAM"),
    ("player ranking, plain",
     "https://matchstats.uefa.com/v1/player-ranking?competitionId=1&seasonYear=2027"
     "&phase=ALL&limit=10&offset=0"),
    ("players list (comp v2)",
     "https://comp.uefa.com/v2/players?competitionId=1&seasonYear=2027&phase=ALL&limit=10&offset=0"),
    ("players list (comp v1)",
     "https://comp.uefa.com/v1/players?competitionId=1&seasonYear=2027&phase=ALL&limit=10&offset=0"),
    ("squad of one club",
     "https://comp.uefa.com/v2/squads?competitionId=1&seasonYear=2027&teamId=52707"),
    ("squad, other spelling",
     "https://comp.uefa.com/v2/teams/52707/squad?competitionId=1&seasonYear=2027"),
    ("player stats",
     "https://matchstats.uefa.com/v1/players/statistics?competitionId=1&seasonYear=2027"
     "&phase=ALL&limit=10&offset=0"),
]

# If any of these answers, the club trivia can be read from UEFA instead of
# being typed out by hand.
CLUB_DETAIL_URLS = [
    ("one club in full",
     "https://comp.uefa.com/v2/teams/52707?competitionId=1&seasonYear=2027"),
    ("clubs with extra fields",
     "https://comp.uefa.com/v2/teams?competitionId=1&seasonYear=2027&phase=ALL"
     "&limit=3&offset=0&optionalFields=VENUE,CITY,FOUNDED,TEAM_DETAIL"),
    ("club profile",
     "https://comp.uefa.com/v2/teams/52707/profile?competitionId=1&seasonYear=2027"),
    ("venues",
     "https://comp.uefa.com/v2/venues?competitionId=1&seasonYear=2027&limit=5&offset=0"),
]

WANT2 = {
    "player name": ("playerName", "name", "internationalName", "displayName", "shortName"),
    "goals":       ("goals", "value", "goalsScored", "totalGoals"),
    "assists":     ("assists", "goalAssist"),
    "their club":  ("clubId", "teamId", "team.id", "teamName", "team.internationalName"),
    "home town":   ("city", "cityName", "town", "venueCity", "homeCity", "venue.city"),
    "founded":     ("founded", "foundationDate", "foundedYear", "yearFounded", "established"),
    "stadium":     ("venue", "venueName", "stadium", "stadiumName", "venue.name"),
    "nickname":    ("nickname", "nickName", "alias", "shortClubName"),
}


def first_object(data):
    """These feeds answer either with a list, or with a wrapper holding one."""
    if isinstance(data, list):
        return data[0] if data else None
    if isinstance(data, dict):
        for k in ("data", "items", "results", "players", "teams", "entities", "content"):
            v = data.get(k)
            if isinstance(v, list) and v:
                return v[0]
            if isinstance(v, dict):
                return v
        return data
    return None


def try_feed(label, url, log, tries=2):
    """Ask once, and once more if it times out - a single timeout proves nothing."""
    log("")
    log("  %s" % label)
    log("  GET %s" % url)
    for attempt in range(1, tries + 1):
        req = urllib.request.Request(url, headers={
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Referer": "https://www.uefa.com/",
            "Origin": "https://www.uefa.com",
        })
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                raw = r.read().decode("utf-8", "replace")
            try:
                data = json.loads(raw)
            except Exception:
                log("    -> answered, but not with JSON (%d characters)" % len(raw))
                log("       starts: %s" % re.sub(r"\s+", " ", raw)[:160])
                return None
            n = len(data) if isinstance(data, list) else "?"
            log("    -> ANSWERED. %s item(s)" % n)
            return data
        except urllib.error.HTTPError as e:
            log("    -> refused: HTTP %s %s" % (e.code, e.reason))
            return None
        except Exception as e:
            log("    -> %s%s" % (e, "  (trying once more)" if attempt < tries else ""))
    return None


def report_fields(data, log):
    obj = first_object(data)
    if not isinstance(obj, dict):
        log("       nothing object-shaped came back.")
        return {}
    flat = flatten(obj)
    log("       every field on the first one:")
    for k in sorted(flat)[:60]:
        v = str(flat[k])
        log("         %-42s %s" % (k[:42], v[:60]))
    if len(flat) > 60:
        log("         ... and %d more fields" % (len(flat) - 60))
    log("       what we were after:")
    for want, names in WANT2.items():
        hit = next((n for n in names if n in flat), None)
        log("         %-12s %s" % (want, ("YES as '%s' = %s" % (hit, str(flat[hit])[:40]))
                                          if hit else "no"))
    return flat


def probe_players(log):
    log("=" * 66)
    log("Probe 2: can we get player names and goals, and the club details")
    log("         the first probe could not find?")
    log("=" * 66)

    log("")
    log("-" * 66)
    log("PART A - players and top scorers")
    log("-" * 66)
    found_any = False
    for label, url in PLAYER_URLS:
        data = try_feed(label, url, log)
        if data is not None:
            found_any = True
            report_fields(data, log)
    if not found_any:
        log("")
        log("   Nothing answered. Top scorers stay out of the comparison box.")

    log("")
    log("-" * 66)
    log("PART B - home town, founded, stadium, nickname")
    log("-" * 66)
    found_b = False
    for label, url in CLUB_DETAIL_URLS:
        data = try_feed(label, url, log)
        if data is not None:
            found_b = True
            report_fields(data, log)
    if not found_b:
        log("")
        log("   Nothing answered. The club trivia has to be typed out by hand")
        log("   and checked by eye - which is what the Word file is for.")

    log("")
    log("-" * 66)
    log("PART C - the top-scorer page, with a longer wait this time")
    log("-" * 66)
    probe_scorers(log)

    log("")
    log("=" * 66)
    log("Copy this whole log into the chat. Whatever answered above is what")
    log("goes in the box; whatever did not is left out rather than invented.")
    log("=" * 66)


# ---------------------------------------------------------------- the test
# ----------------------------------------------- probe 3: who scored?
# UEFA publishes no top-scorer feed we can reach. But we already read every
# match from them. If the goalscorers travel with the match, we can work out
# our own top scorers from Matchdays 1-8 and keep them current for nothing.
# This probe asks exactly that, and nothing else.

PLAYED_DATE = "2026-10-21"      # a Matchday 3 date, long finished

GOAL_WORDS = ("goal", "scor", "event", "player", "squad", "lineup",
              "assist", "card", "substit")


def probe_goals(log):
    log("=" * 66)
    log("Probe 3: do the goalscorers travel with the match?")
    log("=" * 66)
    log("")
    log("-" * 66)
    log("PART A - every single field on one finished match")
    log("-" * 66)

    url = FEED.format(d=PLAYED_DATE)
    data = try_feed("the matches of %s" % PLAYED_DATE, url, log)
    mid = None
    if not isinstance(data, list) or not data:
        log("   The match feed gave nothing back, which is odd - it works daily.")
    else:
        m = data[0]
        flat = flatten(m)
        mid = m.get("id") or flat.get("id")
        log("")
        log("   %d fields on this one match. All of them:" % len(flat))
        for k in sorted(flat):
            log("     %-46s %s" % (k[:46], str(flat[k])[:52]))

        log("")
        log("   -- any field whose NAME hints at goals or players --")
        hits = [k for k in sorted(flat)
                if any(w in k.lower() for w in GOAL_WORDS)]
        if hits:
            for k in hits:
                log("     FOUND  %-42s %s" % (k[:42], str(flat[k])[:52]))
        else:
            log("     none. The match carries the score and nothing about who got them.")

        log("")
        log("   -- and the raw text, in case something is buried --")
        raw = json.dumps(m)
        for w in GOAL_WORDS:
            n = raw.lower().count(w)
            log("     the word %-10s appears %d time(s)" % ("'" + w + "'", n))

    log("")
    log("-" * 66)
    log("PART B - asking for that one match in more detail")
    log("-" * 66)
    if not mid:
        log("")
        log("   No match id to work with, so nothing to try here.")
    else:
        log("")
        log("   the match id is %s" % mid)
        tries = [
            ("that match on its own",
             "https://match.uefa.com/v5/matches/%s?competitionId=1&seasonYear=2027" % mid),
            ("that match, asking for events",
             FEED.format(d=PLAYED_DATE) + "&optionalFields=MATCH_EVENTS,GOALS,SCORERS,PLAYER"),
            ("the events of that match",
             "https://match.uefa.com/v5/matches/%s/events?competitionId=1" % mid),
            ("who played in that match",
             "https://matchstats.uefa.com/v1/matches/%s/players?competitionId=1" % mid),
            ("the line-ups of that match",
             "https://match.uefa.com/v5/matches/%s/lineups?competitionId=1" % mid),
        ]
        for label, u in tries:
            d2 = try_feed(label, u, log)
            if d2 is not None:
                f2 = report_fields(d2, log)
                hits = [k for k in sorted(f2)
                        if any(w in k.lower() for w in GOAL_WORDS)]
                log("       fields hinting at goals or players: %s"
                    % (", ".join(hits[:12]) if hits else "none"))

    log("")
    log("-" * 66)
    log("PART C - one last look for a statistics feed")
    log("-" * 66)
    for label, u in [
        ("player stats on the players feed",
         "https://comp.uefa.com/v2/players?competitionId=1&seasonYear=2027&phase=ALL"
         "&limit=5&offset=0&optionalFields=PLAYER_STATISTICS,STATISTICS,GOALS"),
        ("a statistics feed",
         "https://comp.uefa.com/v2/statistics?competitionId=1&seasonYear=2027&phase=ALL&limit=5&offset=0"),
        ("a player-ranking feed",
         "https://comp.uefa.com/v2/playerrankings?competitionId=1&seasonYear=2027&phase=ALL&limit=5&offset=0"),
    ]:
        d3 = try_feed(label, u, log)
        if d3 is not None:
            f3 = report_fields(d3, log)
            hits = [k for k in sorted(f3) if "goal" in k.lower() or "scor" in k.lower()]
            log("       anything about goals: %s" % (", ".join(hits[:12]) if hits else "no"))

    log("")
    log("=" * 66)
    log("WHAT THIS DECIDES: if goalscorers are in there, I can work out our own")
    log("top scorers from the matchdays and keep them current for free. If they")
    log("are not, top scorers are left out rather than invented. Copy the log in.")
    log("=" * 66)


BUILD = "2026-10-24c"   # printed first, so the log says which copy ran


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "3"
    print("UEFA_test_scraper.py  build %s  ·  asked for: %r" % (BUILD, arg))
    print("(modes this build knows: 3, 4, clubs, players, goals)")
    print("")
    if str(arg).strip().lower().startswith("goal"):
        probe_goals(print)
        return
    if str(arg).strip().lower().startswith("player"):
        probe_players(print)
        return
    if str(arg).strip().lower().startswith("club"):
        probe_clubs(print)
        probe_scorers(print)
        return
    md = int(arg)
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
