"""Write summary.txt - the ONE Premier League email, for Jim and Brien both.

It carries the scores, the closeness factor, the full table and the link. There
is no second email: the paste-ready lines Brien needs are the same twenty lines
of the table, so they are in here too with a note at the end addressed to him.

ONE EMAIL PER MATCHWEEK. The guard is PL_last_emailed.txt, which holds the
number of the matchweek last emailed and is committed to the repo. If that says
the current matchweek has already gone out, nothing is written and nothing is
sent - however many times the job runs. Do not rely on the tables/ folder for
this: a stamp that says what was SENT is the only thing that can prevent a
second send.

The first time it runs with no stamp at all, it writes the stamp and sends
nothing, on the assumption that the matchweek already in the table was emailed
by the old arrangement. That costs one skipped email, once, and saves sending a
duplicate of something already in both inboxes.

Reads   site_template.html   (for both players' locked picks)
        tables/*.csv         (the saved tables)
        PL_last_emailed.txt  (which matchweek has already gone out)
Writes  summary.txt          (only when there is something new to send)
        PL_last_emailed.txt
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
    """The most recent saved table, as {team_id: finishing position}, plus the
    rows themselves and the date in the file name, for printing in the email."""
    best = None
    for fn in sorted(glob.glob(os.path.join(HERE, "tables", "*.csv"))):
        rows = list(csv.DictReader(open(fn, encoding="utf-8")))
        played = int(rows[0]["played"])
        if best is None or played >= best[0]:
            m = re.search(r"_(\d{4}-\d{2}-\d{2})\.csv$", fn)
            best = (played, rows, m.group(1) if m else "")
    if best is None:
        return None, None, None, None
    played, rows, when = best
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
    return played, actual, rows, when


def score(pred, actual):
    """Returns (exact hits, total places off) - the same two numbers the page shows."""
    hits = sum(1 for t, pos in pred.items() if actual[t] == pos)
    off = sum(abs(actual[t] - pos) for t, pos in pred.items())
    return hits, off


def pct(off):
    v = 100 - off / 2.0
    return ("%.1f" % v).rstrip("0").rstrip(".")


STAMP = os.path.join(HERE, "PL_last_emailed.txt")


def drop_summary():
    if os.path.exists(os.path.join(HERE, "summary.txt")):
        os.remove(os.path.join(HERE, "summary.txt"))


def main():
    p = picks()
    week, actual, rows, when = latest_table()
    if actual is None:
        print("No saved tables yet. No summary written.")
        drop_summary()
        return 0

    # One email per matchweek, enforced here and nowhere else.
    prev = ""
    if os.path.exists(STAMP):
        prev = open(STAMP, encoding="utf-8").read().strip()
    if not prev:
        with open(STAMP, "w", encoding="utf-8") as f:
            f.write(str(week))
        print("First run with no stamp. Taking Matchweek %d as already emailed,"
              % week)
        print("and sending nothing this time. The next completed matchweek will")
        print("send one email to both players.")
        drop_summary()
        return 0
    try:
        done = int(prev)
    except ValueError:
        done = -1
    if week <= done:
        print("Matchweek %d has already been emailed (stamp says %s). Nothing to send."
              % (week, prev))
        drop_summary()
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
    # The table itself, in the same email. These are the twenty lines Brien
    # pastes into the page, and they are worth both of them seeing anyway.
    body += ["",
             "-- The table after Matchweek %d --" % week,
             "(from premierleague.com%s)" % (", fetched " + when if when else ""),
             ""]
    body += ["%s. %s %s" % (r["position"], r["team"], r["points"]) for r in rows]

    if week >= 38:
        body += ["", "That is the season done. The final table is in - open the link for the",
                 "Grand Summary and the crowning.",
                 "", "Brien: the champion's points are %s. Enter that under End of season,"
                 % rows[0]["points"],
                 "then open the Grand Summary."]
    else:
        body += ["", "Brien: paste those twenty lines into the Weekly update tab,",
                 "named Week %d." % week]

    open(os.path.join(HERE, "summary.txt"), "w", encoding="utf-8").write("\n".join(body) + "\n")
    with open(STAMP, "w", encoding="utf-8") as f:
        f.write(str(week))
    print("\n".join(body))
    print("")
    print("Stamped Matchweek %d as emailed. It will not be sent again." % week)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("FAILED:", e)
        sys.exit(1)
