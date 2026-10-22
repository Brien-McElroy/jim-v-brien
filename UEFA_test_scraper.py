"""STANDALONE TEST, version 2. Touches nothing else in the repo.

Version 1 told us two useful things:
  * match.uefa.com answers, but the URLs I guessed return 404.
  * the browser never got past the cookie wall, so it only ever read the
    consent notice.

So this version does three things instead of guessing again:
  1. tries harder to dismiss the cookie wall (every frame, many wordings,
     and failing that it deletes the overlay outright),
  2. WATCHES what the page itself asks the network for, and prints any
     address that looks like it carries match data - that tells us UEFA's
     real feed rather than me guessing it,
  3. prints a sample of what it actually read, so the page structure is
     visible even when parsing fails.

It still checks itself against Matchday 3, whose scores we already know.
It never fails the run and never emails anybody.

    python UEFA_test_scraper.py          # Matchday 3 (known answers)
    python UEFA_test_scraper.py 4        # Matchday 4 for real
"""
import json, os, re, sys, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))

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


# ------------------------------------------------------------ cookie wall
CONSENT_TEXTS = ["Reject All", "Reject all", "REJECT ALL", "Decline", "Deny",
                 "Continue without accepting", "Only essential", "Essential only",
                 "Accept All", "Accept all", "ACCEPT ALL", "I Accept", "Accept",
                 "Agree", "I agree", "Got it", "OK", "Allow all", "Save & exit"]
CONSENT_SELECTORS = ["#onetrust-reject-all-handler", "#onetrust-accept-btn-handler",
                     "button[mode='primary']", ".ot-pc-refuse-all-handler",
                     "[data-testid='uc-deny-all-button']",
                     "[data-testid='uc-accept-all-button']",
                     "#CybotCookiebotDialogBodyButtonDecline",
                     ".cookie-accept", "#didomi-notice-agree-button"]


def kill_consent(pg, log):
    """Click the banner away. Try selectors, then button wording, in every
    frame, then just rip the overlay out of the page."""
    done = False
    for sel in CONSENT_SELECTORS:
        for fr in pg.frames:
            try:
                el = fr.query_selector(sel)
                if el and el.is_visible():
                    el.click(timeout=3000)
                    log("    consent: clicked %s" % sel)
                    done = True
                    break
            except Exception:
                pass
        if done:
            break
    if not done:
        for txt in CONSENT_TEXTS:
            for fr in pg.frames:
                try:
                    el = fr.get_by_role("button", name=txt, exact=False).first
                    if el.count() and el.is_visible():
                        el.click(timeout=3000)
                        log("    consent: clicked a button reading %r" % txt)
                        done = True
                        break
                except Exception:
                    pass
            if done:
                break
    pg.wait_for_timeout(2500)
    # Whatever happened, make sure nothing is covering the page.
    try:
        pg.evaluate("""() => {
          const kill = [];
          document.querySelectorAll('div,section,aside,dialog,iframe').forEach(e => {
            const id = ((e.id||'') + ' ' + (e.className||'')).toLowerCase();
            if (/consent|cookie|onetrust|usercentrics|didomi|cybot|gdpr|privacy-?(banner|notice)/.test(id)) kill.push(e);
          });
          kill.forEach(e => e.remove());
          document.documentElement.style.overflow = 'auto';
          document.body.style.overflow = 'auto';
          document.body.style.position = 'static';
        }""")
        log("    consent: stripped any leftover overlay")
    except Exception as e:
        log("    consent: could not strip overlay (%s)" % e)
    return done


# -------------------------------------------------- watch what the page calls
INTERESTING = re.compile(r"(match|fixture|result|score|standing|competition)", re.I)


def sniff(md, log):
    """Open the page and record the data feeds it talks to."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        log("  playwright not installed: %s" % e)
        return None, []

    seen = []          # (url, status, content-type, body sample)
    parsed = None
    urls = ["https://www.uefa.com/uefachampionsleague/fixtures-results/",
            "https://www.uefa.com/uefachampionsleague/standings/"]

    for url in urls:
        log("\n  OPEN %s" % url)
        try:
            with sync_playwright() as p:
                b = p.chromium.launch()
                try:
                    ctx = b.new_context(viewport={"width": 1500, "height": 3000},
                                        locale="en-GB")
                    pg = ctx.new_page()

                    def on_response(r):
                        try:
                            u = r.url
                            ct = (r.headers or {}).get("content-type", "")
                            if "json" not in ct.lower():
                                return
                            if not INTERESTING.search(u):
                                return
                            body = ""
                            try:
                                body = r.text()[:4000]
                            except Exception:
                                pass
                            seen.append((u, r.status, ct, body))
                        except Exception:
                            pass

                    pg.on("response", on_response)
                    pg.goto(url, wait_until="domcontentloaded", timeout=60000)
                    pg.wait_for_timeout(3000)
                    kill_consent(pg, log)
                    pg.wait_for_timeout(4000)
                    for _ in range(14):
                        pg.mouse.wheel(0, 2200)
                        pg.wait_for_timeout(800)
                    txt = pg.inner_text("body")
                finally:
                    b.close()
        except Exception as e:
            log("    -> %s" % str(e).splitlines()[0])
            continue

        log("    read %d characters of page text" % len(txt))
        names = sum(1 for t in ALIASES if re.search(re.escape(t.split()[0]), txt, re.I))
        log("    recognised %d of 36 club names in the text" % names)
        sample = " | ".join(l.strip() for l in txt.splitlines() if l.strip())
        log("    page text begins: %s" % sample[:700])
        if names >= 10:
            log("    ...the real page did load. Looking for Matchday %d." % md)
            got = parse_text(txt, md, log)
            if got:
                parsed = got
                break
        else:
            log("    ...still not the real page content.")
    return parsed, seen


def parse_text(txt, md, log):
    lines = [l.strip() for l in txt.splitlines() if l.strip()]
    want = None
    for i, l in enumerate(lines):
        if re.search(r"matchday\s*%d\b" % md, l, re.I):
            want = i
            break
    if want is None:
        heads = [l for l in lines if re.search(r"matchday", l, re.I)][:6]
        log("    no 'Matchday %d' heading. Headings seen: %s" % (md, heads or "none"))
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
    if not out:
        log("    found the heading but no 'team / goals / team / goals' blocks after it.")
        log("    the 12 lines after it were: %s" % lines[want:want + 13])
    return out or None


def from_feed(seen, md, log):
    """If one of the feeds the page called carries the matches, read it."""
    for url, status, ct, body in seen:
        if not body:
            continue
        try:
            data = json.loads(body)
        except Exception:
            continue
        items = data if isinstance(data, list) else (
            data.get("matches") or data.get("data") or data.get("items") or [])
        if not isinstance(items, list) or not items:
            continue
        out = []
        for m in items:
            if not isinstance(m, dict):
                continue
            h = m.get("homeTeam") or m.get("home") or {}
            a = m.get("awayTeam") or m.get("away") or {}
            if not isinstance(h, dict) or not isinstance(a, dict):
                continue
            hn = (h.get("internationalName") or h.get("displayName")
                  or h.get("teamName") or h.get("name"))
            an = (a.get("internationalName") or a.get("displayName")
                  or a.get("teamName") or a.get("name"))
            sc = m.get("score") or {}
            tot = sc.get("total") if isinstance(sc, dict) else None
            hg = ag = None
            if isinstance(tot, dict):
                hg, ag = tot.get("home"), tot.get("away")
            elif isinstance(sc, dict):
                hg, ag = sc.get("home"), sc.get("away")
            if hg is None or ag is None:
                continue
            H, A = team(hn), team(an)
            if H and A:
                out.append((H, A, int(hg), int(ag)))
        if len(out) >= 9:
            log("  the feed %s carries %d matches" % (url[:110], len(out)))
            return out
    return None


# ---------------------------------------------------------------- the test
def main():
    md = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    checking = (md == 3)
    print("=" * 66)
    print("UEFA scraper test v2 - Matchday %d%s" % (md, "  (answers known)" if checking else ""))
    print("=" * 66)
    log = lambda s: print(s)

    print("\n-- opening the site and listening to what it asks the network for")
    got, seen = sniff(md, log)

    print("\n-- data feeds the page itself called (%d)" % len(seen))
    if not seen:
        print("   none seen. The page may build its content another way.")
    for u, st, ct, body in seen[:25]:
        print("   [%s] %s" % (st, u[:160]))
        if body:
            flat = re.sub(r"\s+", " ", body)[:220]
            print("        %s" % flat)

    if not got and seen:
        print("\n-- trying to read the matches straight out of those feeds")
        got = from_feed(seen, md, log)

    print("\n" + "=" * 66)
    if not got:
        print("VERDICT: still could not read the results.")
        print("Everything above is what I need. Copy the whole log into the chat.")
        print("Meanwhile enter the scores by hand in the page - the game works fine.")
        return

    for h, a, hg, ag in got:
        print("  %-16s %d - %d  %s" % (h, hg, ag, a))
    if len(got) != 18:
        print("\nVERDICT: only %d of 18 matches. Not safe to use yet." % len(got))
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
        print("VERDICT: PASSED. All 18 matches read correctly.")
        print("Tell me and I will wire it into the weekly job.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        print("The test itself crashed: %s" % e)
        traceback.print_exc()
    sys.exit(0)  # never turn the run red
