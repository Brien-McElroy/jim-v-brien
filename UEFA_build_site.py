"""Build Jim's read-only Champions League page from UEFA_state.json.

Reads   UEFA_state.json        (picks, results, bracket - pasted from Brien's Claude page)
        UEFA_site_template.html
Writes  site/uefa/index.html
        UEFA_email.txt         (only when a new matchday has been scored since last time)
"""
import json, os, datetime, sys

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "UEFA_state.json")
TPL = os.path.join(HERE, "UEFA_site_template.html")
OUT_DIR = os.path.join(HERE, "site", "uefa")
MARK = "<!--STATIC-->"
LINK = "https://brien-mcelroy.github.io/jim-v-brien/uefa/"
MDS = [4, 5, 6, 7, 8]


def load_state():
    if not os.path.exists(STATE):
        return {"picks": {"brien": {}, "jim": {}}, "results": {}, "bracket": {}}
    with open(STATE, encoding="utf-8") as f:
        txt = f.read().strip()
    if not txt:
        return {"picks": {"brien": {}, "jim": {}}, "results": {}, "bracket": {}}
    s = json.loads(txt)
    s.setdefault("picks", {}).setdefault("brien", {})
    s["picks"].setdefault("jim", {})
    s.setdefault("results", {})
    s.setdefault("bracket", {"setup": {}, "picks": {"brien": {}, "jim": {}}, "winners": {}})
    return s


def check(state):
    """Fail loudly on data that would silently produce wrong scores."""
    for p in ("brien", "jim"):
        for md, arr in (state["picks"].get(p) or {}).items():
            if not isinstance(arr, list) or len(arr) != 18:
                raise ValueError("%s picks for matchday %s have %s entries, expected 18"
                                 % (p, md, len(arr) if isinstance(arr, list) else "?"))
            for v in arr:
                if v not in ("H", "A", None):
                    raise ValueError("%s matchday %s has an odd pick value: %r" % (p, md, v))
    for k, r in (state["results"] or {}).items():
        s = (r or {}).get("s")
        if not isinstance(s, list) or len(s) != 18:
            raise ValueError("results %s have %s matches, expected 18"
                             % (k, len(s) if isinstance(s, list) else "?"))
        for pair in s:
            if (not isinstance(pair, list) or len(pair) != 2
                    or not all(isinstance(x, int) and 0 <= x <= 19 for x in pair)):
                raise ValueError("results %s contain a bad score: %r" % (k, pair))


def scored_mds(state):
    return [md for md in MDS if ("md%d" % md) in (state["results"] or {})]


def score(state, fixtures):
    """Mirror of the page's own scoring, so the email can never disagree with the page."""
    out = {}
    for p in ("brien", "jim"):
        tot, hit, drew = 0, 0, 0
        per = {}
        for md in scored_mds(state):
            rs = state["results"]["md%d" % md]["s"]
            picks = (state["picks"].get(p) or {}).get(str(md)) or []
            s = 0
            for i in range(18):
                pk = picks[i] if i < len(picks) else None
                if not pk:
                    continue
                hg, ag = rs[i]
                if hg == ag:
                    s += 1
                    drew += 1
                elif (hg > ag and pk == "H") or (ag > hg and pk == "A"):
                    s += 2
                    hit += 1
            per[md] = s
            tot += s
        out[p] = {"pts": tot, "hit": hit, "drew": drew, "per": per}
    return out


def bracket_points(state):
    rounds = [("PO", 8, 2), ("R16", 8, 4), ("QF", 4, 8), ("SF", 2, 16), ("F", 1, 32)]
    bk = state.get("bracket") or {}
    out = {}
    for p in ("brien", "jim"):
        tot, hit = 0, 0
        for k, c, pts in rounds:
            w = (bk.get("winners") or {}).get(k) or []
            pk = ((bk.get("picks") or {}).get(p) or {}).get(k) or []
            for i in range(c):
                if i >= len(w) or w[i] is None:
                    continue
                if i < len(pk) and pk[i] == w[i]:
                    tot += pts
                    hit += 1
        out[p] = {"pts": tot, "hit": hit}
    return out


def main():
    state = load_state()
    check(state)
    with open(os.path.join(HERE, "UEFA_fixtures.json"), encoding="utf-8") as f:
        fixtures = json.load(f)

    today = datetime.date.today().isoformat()
    with open(TPL, encoding="utf-8") as f:
        tpl = f.read()
    if MARK not in tpl:
        raise ValueError("UEFA_site_template.html is missing the %s marker" % MARK)

    inject = ("<script>window.STATIC_MODE=true;window.STATIC_DATE=%s;window.STATIC_DATA=%s;</script>"
              % (json.dumps(today), json.dumps({"picks": state["picks"],
                                                "results": state["results"],
                                                "bracket": state.get("bracket") or {}})))
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(tpl.replace(MARK, inject))
    print("built", os.path.join(OUT_DIR, "index.html"))

    # Jim's picks page - a plain copy, nothing injected. It saves nothing and
    # only hands him a code to send on.
    picks_src = os.path.join(HERE, "UEFA_picks_page.html")
    if os.path.exists(picks_src):
        picks_dir = os.path.join(OUT_DIR, "picks")
        os.makedirs(picks_dir, exist_ok=True)
        with open(picks_src, encoding="utf-8") as f:
            page = f.read()
        with open(os.path.join(picks_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(page)
        print("built", os.path.join(picks_dir, "index.html"))
    else:
        print("UEFA_picks_page.html is not in the repo, so Jim has no picks page.")

    done = scored_mds(state)
    if not done:
        print("No matchdays scored yet; no email.")
        return
    last = max(done)

    # Nobody gets an email until the game has actually started: both players'
    # picks in, and a real betting matchday (4 onwards) scored. Without this,
    # a missing set of picks would mail out a 0 and look like a thrashing.
    def complete(who):
        arr = (state["picks"].get(who) or {}).get(str(last)) or []
        return sum(1 for v in arr if v) == 18

    if last < 4 or not complete("jim") or not complete("brien"):
        waiting = [w.title() for w in ("brien", "jim") if not complete(w)]
        print("Page built, but no email yet for Matchday %d: %s"
              % (last, ("no picks in from " + " and ".join(waiting)) if waiting
                 else "not a betting matchday"))
        if os.path.exists(os.path.join(HERE, "UEFA_email.txt")):
            os.remove(os.path.join(HERE, "UEFA_email.txt"))
        return

    stamp = os.path.join(HERE, "UEFA_last_emailed.txt")
    prev = ""
    if os.path.exists(stamp):
        prev = open(stamp, encoding="utf-8").read().strip()
    if prev == str(last):
        print("Matchday %d was already emailed. Nothing to send." % last)
        if os.path.exists(os.path.join(HERE, "UEFA_email.txt")):
            os.remove(os.path.join(HERE, "UEFA_email.txt"))
        return

    sc = score(state, fixtures)
    bk = bracket_points(state)          # tracked, but never counts towards the crown
    b, j = sc["brien"]["pts"], sc["jim"]["pts"]
    over = last >= 8
    if b > j:
        lead = ("Brien is the 2026/27 Champions League Predictor, by %d." % (b - j)
                if over else "Brien leads by %d." % (b - j))
    elif j > b:
        lead = ("Jim is the 2026/27 Champions League Predictor, by %d." % (j - b)
                if over else "Jim leads by %d." % (j - b))
    else:
        lead = "Level on points - the goal-difference tie-break settles it." if over else "Level."

    body = [
        "Champions League 2026/27 - Brien v Jim, %s Matchday %d."
        % ("the final standings after" if over else "after", last),
        "",
        "  Brien %d" % b,
        "  Jim   %d" % j,
        "  %s" % lead,
        "",
        "This matchday: Brien %d, Jim %d." % (sc["brien"]["per"][last], sc["jim"]["per"][last]),
        "",
        "Open this link for the full table and the running chart:",
        LINK,
        "",
        "Scoring: +2 for the right winner, +1 each if the match was drawn.",
    ]
    if over:
        body += ["",
                 "That is the whole bet - eight matchdays, played for fun, and a crown at the end.",
                 "If you both fancy carrying on, the knockout bracket is on the page. It is scored",
                 "on its own and had nothing to do with the crown."]
        if bk["brien"]["pts"] or bk["jim"]["pts"]:
            body += ["", "Bracket so far (separate): Brien %d, Jim %d."
                     % (bk["brien"]["pts"], bk["jim"]["pts"])]
    with open(os.path.join(HERE, "UEFA_email.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(body) + "\n")
    with open(stamp, "w", encoding="utf-8") as f:
        f.write(str(last))
    print("\n".join(body))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("FAILED:", e)
        sys.exit(1)
