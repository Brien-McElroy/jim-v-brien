"""Notice when something has quietly stopped working, and say so.

The daily job is built so that a failure costs as little as possible: if the
Premier League table cannot be read, the step goes amber and everything else
carries on. That is the right behaviour, but it has a cost - nobody is told.
The table could stop updating for a fortnight and the only sign would be a
warning buried in a log nobody opens.

So: fetch_table.py writes today's date into PL_last_read.txt every time it
manages to read the table, whatever the table said. This script watches that
date. If it falls too far behind, it writes health_warning.txt and the
workflow emails it.

Deliberately NOT based on the newest saved table. The league has two-week
international breaks, so a table that has not moved for twelve days is
perfectly normal. A READER that has not worked for three days is not.

Writes nothing and says nothing when all is well, which is almost always.
"""
import datetime, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
HEARTBEAT = os.path.join(HERE, "PL_last_read.txt")
STAMP = os.path.join(HERE, "health_last_warned.txt")
OUT = os.path.join(HERE, "health_warning.txt")

# How many days of silence before saying something. The job now runs four
# times a day, so three days is twelve consecutive failed attempts - well
# past a passing wobble at ESPN or a bad afternoon on GitHub.
DAYS = 3
# And how long to wait before saying it again, so a long outage does not
# produce an email every six hours.
REPEAT_AFTER = 3


def read_date(path):
    try:
        with open(path, encoding="utf-8") as f:
            return datetime.date.fromisoformat(f.read().strip())
    except Exception:
        return None


def main():
    if os.path.exists(OUT):
        os.remove(OUT)

    # The season being over is not a fault.
    if os.path.exists(os.path.join(HERE, "season_over.flag")):
        print("The season is over. Nothing to watch.")
        return

    today = datetime.date.today()
    last = read_date(HEARTBEAT)

    if last is None:
        # First run after this check was added - start the clock, say nothing.
        print("No heartbeat file yet. Starting the clock today; nothing to report.")
        try:
            with open(HEARTBEAT, "w", encoding="utf-8") as f:
                f.write(today.isoformat())
        except Exception as e:
            print("(could not start the heartbeat: %s)" % e)
        return

    behind = (today - last).days
    if behind < DAYS:
        print("The table was last read %s (%d day(s) ago). All well."
              % (last.isoformat(), behind))
        return

    warned = read_date(STAMP)
    if warned is not None and (today - warned).days < REPEAT_AFTER:
        print("Still behind (%d days), but a warning went out on %s. Not repeating yet."
              % (behind, warned.isoformat()))
        return

    body = [
        "The Premier League table has not been read for %d days." % behind,
        "",
        "The last successful read was %s." % last.strftime("%A %d %B %Y"),
        "",
        "This is the automatic check, not a person. Nothing is broken in the",
        "game itself: the Champions League side is unaffected, every pick and",
        "result already saved is safe, and the pages are still up. What has",
        "stopped is the daily reading of the league table, so Jim's table will",
        "be showing the last one that came through.",
        "",
        "Both places the table is read from would have to be failing for this",
        "to happen - the usual one and the fallback - so it is worth a look.",
        "",
        "To see why: open the repository on GitHub, click Actions, open the",
        "newest 'Weekly Premier League table' run, and read the 'Fetch table'",
        "step. It will say what the sources answered.",
        "",
        "Nothing needs doing in a hurry. Once the table can be read again the",
        "job picks up where it left off on its own, and this email stops.",
    ]
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(body) + "\n")
    with open(STAMP, "w", encoding="utf-8") as f:
        f.write(today.isoformat())
    print("\n".join(body))


if __name__ == "__main__":
    main()
