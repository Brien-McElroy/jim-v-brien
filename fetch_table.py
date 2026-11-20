"""Fetch the Premier League table, save it as tables/MW<nn>_<date>.csv and
write email.txt.

HOW THIS READS THE TABLE, and why it changed on 19 Nov 2026
-----------------------------------------------------------
It used to drive a real browser (Playwright) against premierleague.com,
because that page builds its table in JavaScript and the raw HTML holds no
club names at all. That worked, but it broke twice in nine days:

  11 Nov - installing the browser needed apt, apt could not reach Ubuntu's
           servers, and the whole job died.
  19 Nov - premierleague.com answered the runner with "403 Request blocked"
           (CloudFront) three times and the job died again, taking the
           Champions League half down with it.

Tested from a GitHub runner on 19 Nov, the same table is available as plain
JSON from ESPN, with no browser at all - and its numbers matched the saved
Matchweek 10 table exactly, all twenty rows, positions and points. So JSON
is now the normal route and the browser is only a fallback.

The browser code below is untouched and still correct. If ESPN ever stops
answering, or hands back something that fails the checks, this falls back to
the old method automatically. Losing one does not lose the table.

Run with --dry-run to print what it WOULD save, and compare it against the
newest table already saved, without writing anything.
"""
import csv, datetime, json, re, sys, urllib.request, urllib.error

URL = "https://www.premierleague.com/en/tables/premier-league/2026-27"
ESPN = "https://site.api.espn.com/apis/v2/sports/soccer/eng.1/standings"

TEAMS = ["Arsenal", "Aston Villa", "Bournemouth", "Brentford", "Brighton & Hove Albion",
         "Chelsea", "Coventry City", "Crystal Palace", "Everton", "Fulham", "Hull City",
         "Ipswich Town", "Leeds United", "Liverpool", "Manchester City", "Manchester United",
         "Newcastle United", "Nottingham Forest", "Sunderland", "Tottenham Hotspur"]
# the site sometimes shows short names; map them to the full name
ALIASES = {"Brighton": "Brighton & Hove Albion", "Brighton and Hove Albion": "Brighton & Hove Albion",
           "Man City": "Manchester City", "Man Utd": "Manchester United", "Man United": "Manchester United",
           "Spurs": "Tottenham Hotspur", "Tottenham": "Tottenham Hotspur", "Newcastle": "Newcastle United",
           "Nott'm Forest": "Nottingham Forest", "Forest": "Nottingham Forest", "Leeds": "Leeds United",
           "Hull": "Hull City", "Ipswich": "Ipswich Town", "Coventry": "Coventry City",
           # ESPN's own spellings. Every one of these was checked against the
           # saved Matchweek 10 table on 19 Nov 2026; only Bournemouth differs.
           "AFC Bournemouth": "Bournemouth",
           "Wolverhampton Wanderers": "Wolverhampton Wanderers",
           "West Ham United": "West Ham United"}
NAMES = {t.lower(): t for t in TEAMS}
NAMES.update({k.lower(): v for k, v in ALIASES.items()})


class MidRound(ValueError):
    """Not all teams have played the same number of games yet."""


def check_rows(rows):
    """Shared sanity checks, whichever source the rows came from.

    rows is [(team, played, won, drawn, lost, gf, ga, points)].
    Returns [(position, team, played, points)] in table order.
    Anything that does not add up raises, so a changed feed or layout fails
    loudly instead of quietly saving a wrong table into the game.
    """
    if len(rows) != 20:
        raise ValueError("Read %d of 20 teams" % len(rows))
    if len({r[0] for r in rows}) != 20:
        raise ValueError("The same club appeared twice")
    for team, pl, w, d, l, gf, ga, pts in rows:
        if pl != w + d + l:
            raise ValueError("%s: played %d but W+D+L is %d" % (team, pl, w + d + l))
        if pts != 3 * w + d:
            raise ValueError("%s: points %d but 3W+D is %d" % (team, pts, 3 * w + d))
    if len({r[1] for r in rows}) != 1:
        raise MidRound("Teams have played different numbers of games; table may be mid-round")

    # Official order: points, then goal difference, then goals scored.
    ordered = sorted(rows, key=lambda r: (-r[7], -(r[5] - r[6]), -r[5], r[0]))
    return [(n + 1, r[0], r[1], r[7]) for n, r in enumerate(ordered)]


def fetch_espn():
    """Read the table from ESPN's standings feed. No browser needed."""
    req = urllib.request.Request(ESPN, headers={
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
        "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=45) as r:
        data = json.loads(r.read())

    # Make sure this is the right season before trusting a single number.
    season = (data.get("season") or {}).get("displayName", "")
    if "2026-27" not in season and "2026/27" not in season:
        raise ValueError("ESPN is serving season %r, not 2026-27" % season)

    entries = data["children"][0]["standings"]["entries"]
    rows = []
    for e in entries:
        raw = e["team"].get("displayName") or e["team"].get("name") or ""
        team = NAMES.get(raw.lower())
        if not team:
            # Never guess a club name - the game is scored on exact positions,
            # so an unrecognised name has to stop the run, not be approximated.
            raise ValueError("ESPN club name not recognised: %r. Add it to ALIASES." % raw)
        s = {x.get("name"): x for x in e["stats"]}

        def num(key):
            v = s.get(key)
            if v is None:
                raise ValueError("%s: ESPN did not supply %s" % (team, key))
            n = v.get("value")
            if n is None:
                n = v.get("displayValue")
            return int(float(n))

        rows.append((team, num("gamesPlayed"), num("wins"), num("ties"), num("losses"),
                     num("pointsFor"), num("pointsAgainst"), num("points")))
    return rows


def parse(text):
    """Return [(pos, team, played, pts)] in table order, or raise ValueError.
    Reads the page text line by line: a team-name line is followed by the numbers
    Pl W D L GF GA GD Pts. Every row is checked (Pl = W+D+L, Pts = 3W+D) so a
    layout change causes a clear failure instead of wrong data."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    rows, seen = [], set()
    for i, line in enumerate(lines):
        team = NAMES.get(line.lower())
        if not team or team in seen:
            continue
        nums = []
        for nxt in lines[i + 1:i + 14]:
            if NAMES.get(nxt.lower()):
                break
            if re.fullmatch(r"[+\-−]?\d+", nxt):
                nums.append(int(nxt.replace("−", "-")))
            if len(nums) == 8:
                break
        if len(nums) < 8:
            continue
        pl, w, d, l, gf, ga, gd, pts = nums
        if pl != w + d + l or pts != 3 * w + d or gd != gf - ga:
            continue
        seen.add(team)
        rows.append((team, pl, pts))
    if len(rows) != 20:
        raise ValueError("Read %d of 20 teams from the page" % len(rows))
    pts = [r[2] for r in rows]
    if pts != sorted(pts, reverse=True):
        raise ValueError("Rows are not in points order")
    if len({r[1] for r in rows}) != 1:
        raise MidRound("Teams have played different numbers of games; table may be mid-round")
    return [(n + 1, t, p, s) for n, (t, p, s) in enumerate(rows)]


def fetch_text():
    """Load the page, retrying up to 3 times. We wait for the table itself to appear
    rather than for the whole page to go quiet, because the site keeps loading ads."""
    import time
    from playwright.sync_api import sync_playwright
    last = None
    for attempt in range(3):
        try:
            with sync_playwright() as p:
                b = p.chromium.launch()
                try:
                    pg = b.new_page(viewport={"width": 1400, "height": 2400})
                    pg.goto(URL, wait_until="domcontentloaded", timeout=60000)
                    for sel in ("#onetrust-reject-all-handler", "#onetrust-accept-btn-handler"):
                        try:
                            pg.click(sel, timeout=3000); break
                        except Exception:
                            pass
                    # Wait until the VISIBLE page text holds a readable table. (Waiting on the
                    # word "Arsenal" fails: it also sits, hidden, in the site's club menu.)
                    def readable():
                        try:
                            parse(pg.inner_text("body")); return True
                        except MidRound:
                            return True
                        except ValueError:
                            return False
                    clicked = False
                    for _ in range(30):
                        if readable():
                            break
                        if not clicked:
                            # the default "Short" view lacks draws and losses; "Full" has every column
                            try:
                                pg.get_by_text("Full", exact=True).first.click(timeout=3000)
                                clicked = True
                            except Exception:
                                pass
                        pg.wait_for_timeout(3000)
                    else:
                        t = pg.inner_text("body")
                        print("Page text seen (first 800 chars):", t[:800].replace("\n", " | "))
                        raise RuntimeError("Table never became readable on the page")
                    return pg.inner_text("body")
                finally:
                    b.close()
        except Exception as e:
            last = e
            print("Attempt %d failed: %s" % (attempt + 1, str(e).splitlines()[0]))
            time.sleep(10)
    raise last


def get_rows():
    """ESPN first, the browser second. Returns [(pos, team, played, pts)].

    A MidRound from either source means the matchweek is still being played;
    that is normal and must not be retried against the other source.
    """
    try:
        print("Reading the table from ESPN...")
        rows = check_rows(fetch_espn())
        print("ESPN gave a complete, consistent table.")
        return rows
    except MidRound:
        raise
    except Exception as e:
        print("ESPN did not work out (%s). Falling back to the browser." % e)
    return parse(fetch_text())


def beat(dry):
    """Record that the table was read today, whatever it said.

    This is the heartbeat check_health.py watches. It is deliberately NOT the
    date of the newest saved table: the league has two-week international
    breaks, so a table that has not moved is normal and would cry wolf. A
    reader that has not managed to READ for days is not normal, and that is
    the thing nobody would otherwise notice.
    """
    if dry:
        return
    try:
        with open("PL_last_read.txt", "w", encoding="utf-8") as f:
            f.write(datetime.date.today().isoformat())
    except Exception as e:                       # never let the heartbeat break the run
        print("(could not write the heartbeat file: %s)" % e)


if __name__ == "__main__":
    import glob, os
    dry = "--dry-run" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    try:
        rows = parse(open(args[0], encoding="utf-8").read()) if args else get_rows()
    except MidRound as e:
        # A matchweek is still being played. This is normal, so finish quietly (no red failure, no email).
        # The table WAS read, so this still counts as a heartbeat.
        beat(dry)
        print("Matchweek still in progress, nothing to do:", e)
        if not dry and os.path.exists("email.txt"): os.remove("email.txt")
        sys.exit(0)
    except Exception as e:
        print("FAILED:", e); sys.exit(1)
    beat(dry)
    today = datetime.date.today().isoformat()
    played = rows[0][2]

    if dry:
        print("\n--- what would be saved (nothing was written) ---")
        print("position,team,played,points")
        for r in rows:
            print("%d,%s,%d,%d" % r)
        newest = sorted(glob.glob("tables/*.csv"))[-1] if glob.glob("tables/*.csv") else None
        if newest:
            old = list(csv.DictReader(open(newest, encoding="utf-8")))
            print("\n--- compared with %s ---" % newest)
            if int(old[0]["played"]) != played:
                print("Different matchweek (saved %s played, feed says %d), so no row-by-row check."
                      % (old[0]["played"], played))
            else:
                bad = [(o["position"], o["team"], o["points"], r)
                       for o, r in zip(old, rows)
                       if (int(o["position"]), o["team"], int(o["points"])) != (r[0], r[1], r[3])]
                if bad:
                    print("MISMATCH on %d row(s):" % len(bad))
                    for o_pos, o_team, o_pts, r in bad:
                        print("   saved: %s %s %s   feed: %d %s %d" % (o_pos, o_team, o_pts, r[0], r[1], r[3]))
                else:
                    print("IDENTICAL on all 20 rows - position, club and points.")
        sys.exit(0)

    os.makedirs("tables", exist_ok=True)
    # Run every day, but only act when ALL 20 teams have played one more game than
    # the last saved table. That is exactly "after Matchweek X is complete and
    # before Matchweek X+1 has started". Mid-round tables were rejected above.
    have = set()
    for fn in glob.glob("tables/*.csv"):
        try:
            have.add(int(list(csv.DictReader(open(fn, encoding="utf-8")))[0]["played"]))
        except Exception:
            pass
    if played in have or played < max(have, default=0):
        print("Matchweek %d is already saved or nothing new. Nothing to send." % played)
        if os.path.exists("email.txt"): os.remove("email.txt")
        sys.exit(0)
    with open("tables/MW%02d_%s.csv" % (played, today), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["position", "team", "played", "points"]); w.writerows(rows)
    body = ["Premier League 2026-27 table after Matchweek %d (fetched %s)." % (played, today),
            "Source: " + URL, "",
            "Jim's results page (updates itself in a few minutes): https://brien-mcelroy.github.io/jim-v-brien/", "",
            "Paste the lines below into the Weekly update tab (name it Week %d):" % played, ""]
    body += ["%d. %s %d" % (pos, team, pts) for pos, team, _, pts in rows]
    if played >= 38:
        body += ["", "This is the FINAL table of the season. Weekly updates have now been switched off.",
                 "Champion's points: %d. Enter it under End of season, then open the Grand Summary." % rows[0][3]]
    open("email.txt", "w", encoding="utf-8").write("\n".join(body) + "\n")
    if played >= 38:
        open("season_over.flag", "w").write("done")
    print("\n".join(body))
