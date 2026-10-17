"""Fetch the official Premier League table, save it as tables/<date>.csv and
write email.txt (plain text, ready to paste into the Jim v Brien page)."""
import csv, datetime, re, sys
from playwright.sync_api import sync_playwright

URL = "https://www.premierleague.com/en/tables/premier-league/2026-27"
TEAMS = ["Arsenal", "Aston Villa", "Bournemouth", "Brentford", "Brighton & Hove Albion",
         "Chelsea", "Coventry City", "Crystal Palace", "Everton", "Fulham", "Hull City",
         "Ipswich Town", "Leeds United", "Liverpool", "Manchester City", "Manchester United",
         "Newcastle United", "Nottingham Forest", "Sunderland", "Tottenham Hotspur"]
# the site sometimes shows short names; map them to the full name
ALIASES = {"Brighton": "Brighton & Hove Albion", "Brighton and Hove Albion": "Brighton & Hove Albion",
           "Man City": "Manchester City", "Man Utd": "Manchester United", "Man United": "Manchester United",
           "Spurs": "Tottenham Hotspur", "Tottenham": "Tottenham Hotspur", "Newcastle": "Newcastle United",
           "Nott'm Forest": "Nottingham Forest", "Forest": "Nottingham Forest", "Leeds": "Leeds United",
           "Hull": "Hull City", "Ipswich": "Ipswich Town", "Coventry": "Coventry City"}
NAMES = {t.lower(): t for t in TEAMS}
NAMES.update({k.lower(): v for k, v in ALIASES.items()})


class MidRound(ValueError):
    """Not all teams have played the same number of games yet."""


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
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1400, "height": 2400})
        pg.goto(URL, wait_until="networkidle", timeout=90000)
        for sel in ("#onetrust-reject-all-handler", "#onetrust-accept-btn-handler"):
            try:
                pg.click(sel, timeout=3000); break
            except Exception:
                pass
        pg.wait_for_timeout(4000)
        # the default "Short" view lacks draws and losses; "Full" has every column
        try:
            pg.get_by_text("Full", exact=True).first.click(timeout=5000)
            pg.wait_for_timeout(2500)
        except Exception:
            pass
        text = pg.inner_text("body")
        b.close()
    return text


if __name__ == "__main__":
    import glob, os
    try:
        rows = parse(open(sys.argv[1], encoding="utf-8").read() if len(sys.argv) > 1 else fetch_text())
    except MidRound as e:
        # A matchweek is still being played. This is normal, so finish quietly (no red failure, no email).
        print("Matchweek still in progress, nothing to do:", e)
        if os.path.exists("email.txt"): os.remove("email.txt")
        sys.exit(0)
    except Exception as e:
        print("FAILED:", e); sys.exit(1)
    today = datetime.date.today().isoformat()
    played = rows[0][2]
    os.makedirs("tables", exist_ok=True)
    # Run every day, but only act when ALL 20 teams have played one more game than
    # the last saved table. That is exactly "after Matchweek X is complete and
    # before Matchweek X+1 has started". Mid-round tables were rejected in parse().
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
