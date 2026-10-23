"""Write summary.txt - the short Premier League results note for Jim and Brien.

Only runs when fetch_table.py has produced email.txt, which is its signal that a
new matchweek was saved. No email.txt means nothing new, so nothing is written.

The paste-ready table in email.txt still goes to Brien alone. This is the short
version both players get.

Reads   email.txt            (only as the "something new happened" signal)
        site_template.html   (for both players' locked picks)
        tables/*.csv         (the saved tables)
Writes  summary.txt
"""
import csv, glob, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
LINK = "https://brien-mcelroy.github.io/jim-v-brien/"

NAME2ID = {"Arsenal": "ars", "Aston Villa": "avl", "Bournemouth": "bou", "Brentford": "bre",
           "Brighton & Hove Albion": "bha", "Chelsea": "che", "Coventry City": "cov",
           "Crystal Palace": "cry", "Everton": "eve", "Fulham": "ful", "Hull City": "hul",
           "Ipswich Town": "ips", "Leeds United": "lee", "Liverpool": "liv",
           "Manchester City": "mci", "Manchester United": "mun", "Newcastle United": "new",
           "Nottingham Forest": "nfo", "Sunderland": "sun", "Tottenham Hotspur": "tot"}


def picks():
    """Lift the two locked lists out of the page template, so there is only ever
    one copy of them in the repo."""
    tpl = open(os.path.join(HERE, "site_template.html"), encoding="utf-8").read()
    m = re.search(r"var PICKS=(\{.*?\})\s*,\s*CHAMP=", tpl, re.S)
    if not m:
        raise ValueError("Could not find PICKS in site_template.html")
    p = json.loads(m.group(1))
    for who in ("jim", "brien"):
        if sorted(p[who].values()) != list(range(1, 21)):
            raise ValueError("%s's picks are not a clean 1-20" % who)
    return p


def latest_table():
    """The most recent saved table, as {team_id: finishing position}."""
    best = None
    for fn in sorted(glob.glob(os.path.join(HERE, "tables", "*.csv"))):
        rows = list(csv.DictReader(open(fn, encoding="utf-8")))
        played = int(rows[0]["played"])
        if best is None or played >= best[0]:
            best = (played, rows)
    if best is None:
        return None, None
    played, rows = best
    if len(rows) != 20:
        raise ValueError("Latest table has %d rows, expected 20" % len(rows))
    actual = {}
    for r in rows:
        tid = NAME2ID.get(r["team"])
        if not tid:
            raise ValueError("Unknown team in the saved table: %r" % r["team"])
        actual[tid] = int(r["position"])
    if sorted(actual.values()) != list(range(1, 21)):
        raise ValueError("Latest table is not a clean 1-20")
    return played, actual


def score(pred, actual):
    """Returns (exact hits, total places off) - the same two numbers the page shows."""
    hits = sum(1 for t, pos in pred.items() if actual[t] == pos)
    off = sum(abs(actual[t] - pos) for t, pos in pred.items())
    return hits, off


def pct(off):
    v = 100 - off / 2.0
    return ("%.1f" % v).rstrip("0").rstrip(".")


def main():
    if not os.path.exists(os.path.join(HERE, "email.txt")):
        print("No email.txt, so nothing new this run. No summary written.")
        if os.path.exists(os.path.join(HERE, "summary.txt")):
            os.remove(os.path.join(HERE, "summary.txt"))
        return 0

    p = picks()
    week, actual = latest_table()
    if actual is None:
        print("No saved tables yet. No summary written.")
        return 0

    jh, jo = score(p["jim"], actual)
    bh, bo = score(p["brien"], actual)

    if jh != bh:
        who = "Jim" if jh > bh else "Brien"
        lead = "%s leads by %d." % (who, abs(jh - bh))
    elif jo != bo:
        who = "Jim" if jo < bo else "Brien"
        lead = "%s leads on closeness." % who
    else:
        lead = "Dead level."

    body = [
        "Premier League 2026-27 - Jim v Brien, after Matchweek %d." % week,
        "",
        "  Jim    %d" % jh,
        "  Brien  %d" % bh,
        "  %s" % lead,
        "",
        "Closeness factor: Jim %s%%, Brien %s%%." % (pct(jo), pct(bo)),
        "Places off: Jim %d, Brien %d." % (jo, bo),
        "",
        "Open this link for the full table and the running chart:",
        LINK,
        "",
        "Scoring: 1 point for every club in exactly the right place.",
    ]
    if week >= 38:
        body += ["", "That is the season done. The final table is in - open the link for the",
                 "Grand Summary and the crowning."]
    open(os.path.join(HERE, "summary.txt"), "w", encoding="utf-8").write("\n".join(body) + "\n")
    print("\n".join(body))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("FAILED:", e)
        sys.exit(1)
