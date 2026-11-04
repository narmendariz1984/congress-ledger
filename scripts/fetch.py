#!/usr/bin/env python3
"""Refresh site/data/ledger.json for the Congress Bill Ledger.

Sources
  - Congress.gov API v3 (bills, actions, cosponsors, House roll calls beta)
  - Voteview Senate roll calls (CSV); senate.gov refuses automated clients
  - data/curated.json (hand-curated layer; always wins over fetched fields)

The API key is read from the CONGRESS_API_KEY environment variable only.
It is never written to disk or printed.

Modes (MODE env var)
  auto   decide from the clock and the session calendar (used by the schedule)
  full   refresh bills and votes now
  votes  refresh votes only
  offline  no network; rebuild from curated + last ledger (for testing)

Standard library only, so the workflow needs no installs.
"""
from __future__ import annotations

import datetime as dt
import csv
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CURATED = ROOT / "data" / "curated.json"
TRACKED = ROOT / "data" / "tracked.json"          # bills found by discovery
OUT = ROOT / "site" / "data" / "ledger.json"

API = "https://api.congress.gov/v3"
UA = "congress-ledger/1.0 (+https://github.com/narmendariz1984/congress-ledger)"
CT = dt.timezone(dt.timedelta(hours=-6))          # display only; logic uses UTC dates

WARN: list[str] = []


def warn(msg: str) -> None:
    WARN.append(msg)
    print(f"warning: {msg}", file=sys.stderr)


# ---------------------------------------------------------------- http

def _get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 500, 502, 503, 504):
                ra = e.headers.get("Retry-After", "") if e.headers else ""
                wait = int(ra) if ra.isdigit() else 2 * (attempt + 1)
                time.sleep(min(wait, 60))
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise last  # type: ignore[misc]


def api(path: str, **params) -> dict:
    key = os.environ.get("CONGRESS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("CONGRESS_API_KEY is not set")
    params = {"format": "json", **params, "api_key": key}
    url = f"{API}/{path.lstrip('/')}?{urllib.parse.urlencode(params)}"
    try:
        return json.loads(_get(url))
    except urllib.error.HTTPError as e:
        # never echo the URL: it carries the key
        raise RuntimeError(f"Congress.gov API {e.code} on /{path.split('?')[0]}") from None


def api_all(path: str, list_key: str, limit: int = 250, cap: int = 2000, **params) -> list:
    out, offset = [], 0
    while offset < cap:
        page = api(path, limit=limit, offset=offset, **params)
        items = page.get(list_key) or []
        out.extend(items)
        if not (page.get("pagination") or {}).get("next") or not items:
            break
        offset += limit
    return out


# ---------------------------------------------------------------- helpers

TYPE_SLUG = {
    "hr": "house-bill", "s": "senate-bill",
    "hjres": "house-joint-resolution", "sjres": "senate-joint-resolution",
    "hres": "house-resolution", "sres": "senate-resolution",
    "hconres": "house-concurrent-resolution", "sconres": "senate-concurrent-resolution",
}
TYPE_LABEL = {
    "hr": "H.R.", "s": "S.", "hjres": "H.J.Res.", "sjres": "S.J.Res.",
    "hres": "H.Res.", "sres": "S.Res.", "hconres": "H.Con.Res.", "sconres": "S.Con.Res.",
}
AREA_MAP = {
    "Health": "Health care",
    "Taxation": "Taxation",
    "Housing and Community Development": "Housing",
    "Economics and Public Finance": "Budget & appropriations",
    "Civil Rights and Liberties, Minority Issues": "Civil rights",
    "Immigration": "Immigration",
    "Labor and Employment": "Labor & wages",
    "Energy": "Climate & energy",
    "Environmental Protection": "Climate & energy",
    "Crime and Law Enforcement": "Courts & justice",
    "Law": "Courts & justice",
    "Families": "Child care",
    "Social Welfare": "Child care",
    "Government Operations and Politics": "Accountability & oversight",
}


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def congress_url(congress: int, btype: str, number: int) -> str:
    return f"https://www.congress.gov/bill/{ordinal(congress)}-congress/{TYPE_SLUG.get(btype, btype)}/{number}"


def current_congress(today: dt.date) -> tuple[int, int]:
    """(congress, session) for a date. Congress n starts Jan 3 of year 1789 + 2(n-1)."""
    y = today.year
    if today < dt.date(y, 1, 3):
        y -= 1
    congress = (y - 1789) // 2 + 1
    session = 1 if (y - 1789) % 2 == 0 else 2
    return congress, session


def bill_id(congress: int, btype: str, number: int) -> str:
    return f"{congress}-{btype.lower()}{int(number)}"


# ---------------------------------------------------------------- stage logic

STAGE_RULES = [
    (6, re.compile(r"became public law|signed by president", re.I)),
    (5, re.compile(r"presented to president", re.I)),
]
PASSED_H = re.compile(r"passed/agreed to in house|on passage passed|on motion to suspend the rules and pass the bill.*agreed", re.I)
PASSED_S = re.compile(r"passed/agreed to in senate|passed senate", re.I)
FLOOR = re.compile(r"cloture|motion to proceed|considered under|considered by senate|rule h\. ?res|discharge|failed of passage|on passage", re.I)
COMMITTEE = re.compile(r"reported|ordered to be reported|markup|committee consideration|placed on (the )?(union|house|senate legislative) calendar", re.I)
VETO = re.compile(r"vetoed by president", re.I)
# Auto-tracking bar: a recorded floor event, not just committee work
MATURE_HINT = re.compile(r"passed|agreed to|on passage|cloture|discharge|presented to president|became public law|vetoed|failed of passage|not invoked", re.I)
STRONG = re.compile(r"passed/agreed to in (house|senate)|passed senate|on passage|cloture|motion to discharge|discharge petition|presented to president|became public law|vetoed|failed of passage", re.I)


def derive(actions: list[dict], laws: list) -> dict:
    texts = [(a.get("actionDate") or "", a.get("text") or "") for a in actions]
    all_text = " \n".join(t for _, t in texts)
    stage = 0
    if COMMITTEE.search(all_text):
        stage = max(stage, 1)
    if FLOOR.search(all_text):
        stage = max(stage, 2)
    ph, ps = bool(PASSED_H.search(all_text)), bool(PASSED_S.search(all_text))
    if ph or ps:
        stage = max(stage, 3)
    if ph and ps:
        stage = max(stage, 4)
    for s, rx in STAGE_RULES:
        if rx.search(all_text):
            stage = max(stage, s)
    if laws:
        stage = 6
    if stage == 6:
        status = "law"
    elif VETO.search(all_text):
        status = "vetoed"
    elif stage >= 3:
        status = "passed1"
    else:
        status = "moving"
    return {"reached": stage, "status": status, "strong": bool(STRONG.search(all_text) or laws)}


MILESTONE = re.compile(
    r"^introduced in|reported|passed|agreed to|cloture|presented to president|became public law|vetoed|"
    r"discharge|failed|not invoked|motion to proceed", re.I)


def chamber_of(text: str, action: dict) -> str:
    src = ((action.get("sourceSystem") or {}).get("name") or "").lower()
    if "house" in src:
        return "H"
    if "senate" in src:
        return "S"
    if re.search(r"\bin house\b|house\b", text, re.I):
        return "H"
    if re.search(r"\bin senate\b|senate\b", text, re.I):
        return "S"
    return "—"


TALLY = re.compile(r"(\d{1,3})\s*-\s*(\d{1,3})")


def timeline_from(actions: list[dict]) -> list[dict]:
    seen, out = set(), []
    for a in sorted(actions, key=lambda a: a.get("actionDate") or ""):
        text = (a.get("text") or "").strip()
        if not text or not MILESTONE.search(text):
            continue
        key = (a.get("actionDate"), text[:80])
        if key in seen:
            continue
        seen.add(key)
        m = TALLY.search(text)
        ev = {"d": a.get("actionDate"), "ch": chamber_of(text, a), "e": text[:160], "fn": "cg"}
        if m:
            ev["v"] = f"{m.group(1)}–{m.group(2)}"
        if re.search(r"became public law", text, re.I):
            ev["k"] = "win"
        elif re.search(r"not invoked|failed|vetoed", text, re.I):
            ev["k"] = "kill"
        out.append(ev)
    return out[-10:]


def parse_member(s: dict) -> dict:
    name = s.get("fullName") or " ".join(x for x in (s.get("firstName"), s.get("lastName")) if x)
    name = re.sub(r"^(Rep\.|Sen\.|Del\.|Resident Commissioner)\s+", "", name or "")
    name = re.sub(r"\s*\[[^\]]*\]\s*$", "", name)
    if "," in name:  # "Arrington, Jodey C." -> "Jodey C. Arrington"
        last, first = [x.strip() for x in name.split(",", 1)]
        name = f"{first} {last}"
    st = s.get("state") or ""
    dist = s.get("district")
    return {"n": name.strip(), "p": (s.get("party") or "")[:1], "s": f"{st}-{dist}" if dist not in (None, "", 0) else st}


# ---------------------------------------------------------------- bills

def fetch_bill(congress: int, btype: str, number: int) -> dict:
    path = f"bill/{congress}/{btype}/{number}"
    b = (api(path).get("bill")) or {}
    actions = api_all(f"{path}/actions", "actions")
    cos = api_all(f"{path}/cosponsors", "cosponsors")
    cos = [c for c in cos if not c.get("sponsorshipWithdrawnDate")]
    split = {"t": len(cos), "d": 0, "r": 0, "i": 0}
    for c in cos:
        p = (c.get("party") or "").upper()[:1]
        split["d" if p == "D" else "r" if p == "R" else "i"] += 1
    sponsors = b.get("sponsors") or []
    laws = b.get("laws") or []
    out = {
        "congress": congress, "type": btype, "number": number,
        "num": f"{TYPE_LABEL.get(btype, btype.upper())} {number}",
        "title": b.get("title") or "",
        "introduced": b.get("introducedDate"),
        "sponsor": parse_member(sponsors[0]) if sponsors else None,
        "cosponsors": split,
        "area": AREA_MAP.get(((b.get("policyArea") or {}).get("name") or ""), (b.get("policyArea") or {}).get("name") or "Other"),
        "latest": b.get("latestAction") or {},
        "url": congress_url(congress, btype, number),
        "timeline": timeline_from(actions),
        **derive(actions, laws),
    }
    if laws:
        ln = laws[0].get("number")
        out["law"] = f"Pub. L. {ln}" if ln else "Public law"
        out["outcome"] = {"where": "Signed into law", "by": "", "d": (b.get("latestAction") or {}).get("actionDate"), "v": "", "fn": "cg"}
    return out


def discover(congress: int, since: dt.datetime) -> list[tuple[str, int]]:
    """Bills in this Congress updated since `since` whose latest action looks mature."""
    found = []
    try:
        items = api_all(f"bill/{congress}", "bills", cap=3000, sort="updateDate desc",
                        fromDateTime=since.strftime("%Y-%m-%dT%H:%M:%SZ"))
    except Exception as e:  # noqa: BLE001
        warn(f"discovery failed: {e}")
        return found
    for it in items:
        text = ((it.get("latestAction") or {}).get("text") or "")
        btype = (it.get("type") or "").lower()
        if btype in ("hres", "sres", "hconres", "sconres"):
            continue  # simple/concurrent resolutions don't become law
        if MATURE_HINT.search(text) and not re.search(r"referred to", text, re.I):
            try:
                found.append((btype, int(it.get("number"))))
            except (TypeError, ValueError):
                pass
    return found


# ---------------------------------------------------------------- votes

def senate_votes(congress: int, session: int) -> list[dict] | None:
    """Senate roll calls from Voteview (UCLA), which publishes them for reuse.

    senate.gov answers automated clients with 403 from both GitHub and a home
    connection, so we don't ask it. Voteview usually lags a vote by a few hours.
    """
    url = f"https://voteview.com/static/data/out/rollcalls/S{congress}_rollcalls.csv"
    try:
        rows = list(csv.DictReader(io.StringIO(_get(url, timeout=60).decode("utf-8-sig"))))
    except Exception as e:  # noqa: BLE001
        code = getattr(e, "code", "")
        warn(f"Senate votes (Voteview) unavailable ({e.__class__.__name__} {code})".strip())
        return None
    out = []
    for r in rows:
        if (r.get("chamber") or "Senate") != "Senate" or str(r.get("session") or session) != str(session):
            continue
        num = (r.get("clerk_rollnumber") or r.get("rollnumber") or "").strip()
        n = int(float(num)) if num.replace(".", "", 1).isdigit() else num
        def cnt(k: str) -> str:
            v = (r.get(k) or "").strip()
            return str(int(float(v))) if v.replace(".", "", 1).isdigit() else v
        desc = re.sub(r"\s+", " ", (r.get("vote_desc") or r.get("dtl_desc") or "").strip())
        out.append({
            "ch": "S", "n": n, "d": (r.get("date") or "").strip()[:10],
            "q": re.sub(r"\s+", " ", (r.get("vote_question") or "").strip()),
            "measure": (r.get("bill_number") or "").strip(),
            "issue": (r.get("bill_number") or "").strip(),
            "title": desc[:200],
            "result": (r.get("vote_result") or "").strip(),
            "y": cnt("yea_count"), "n_": cnt("nay_count"),
            "u": f"https://www.senate.gov/legislative/LIS/roll_call_votes/vote{congress}{session}/vote_{congress}_{session}_{n:05d}.htm" if isinstance(n, int) else "",
        })
    out.sort(key=lambda x: (x["d"], x["n"] if isinstance(x["n"], int) else 0), reverse=True)
    return out[:60]


def house_votes(congress: int, session: int) -> list[dict]:
    """Congress.gov House roll call endpoint (beta). Parsed defensively."""
    try:
        page = api(f"house-vote/{congress}/{session}", limit=60)
    except Exception as e:  # noqa: BLE001
        warn(f"House votes unavailable ({e})")
        return []
    items = next((page[k] for k in page if isinstance(page[k], list)), [])
    out = []
    for v in items:
        if not isinstance(v, dict):
            continue
        num = v.get("rollCallNumber") or v.get("rollNumber")
        leg = " ".join(str(x) for x in (v.get("legislationType"), v.get("legislationNumber")) if x)
        out.append({
            "ch": "H", "n": num, "d": (v.get("startDate") or v.get("date") or "")[:10],
            "q": v.get("voteQuestion") or v.get("question") or v.get("voteType") or "",
            "measure": leg, "title": "", "result": v.get("result") or "",
            "y": "", "n_": "",
            "u": f"https://clerk.house.gov/Votes/{(v.get('startDate') or '')[:4]}{num}" if num else "",
        })
    out.sort(key=lambda x: (x["d"], x["n"] or 0), reverse=True)
    return out[:60]


def senate_with_backoff(congress: int, session: int, now: dt.datetime, state: dict, previous: list) -> list:
    """Ask for Senate votes at most once per backoff window after a failure.

    1st failure waits 1h, then 2h, 4h, 8h, 16h, capped at 24h. One success resets it.
    While waiting, the last good list is kept.
    """
    b = state.setdefault("senateBackoff", {"failures": 0, "nextTry": None})
    if b.get("nextTry") and now < dt.datetime.fromisoformat(b["nextTry"]):
        print(f"Senate votes: backing off until {b['nextTry']}")
        return previous
    got = senate_votes(congress, session)
    if got is None:
        b["failures"] = int(b.get("failures") or 0) + 1
        wait = min(2 ** (b["failures"] - 1), 24)
        b["nextTry"] = (now + dt.timedelta(hours=wait)).isoformat(timespec="seconds")
        print(f"Senate votes: failure {b['failures']}, next try in {wait}h")
        return previous
    b["failures"], b["nextTry"] = 0, None
    return got


# ---------------------------------------------------------------- calendar

def session_days(ranges: list[dict]) -> set[str]:
    days = set()
    for r in ranges or []:
        try:
            d, end = dt.date.fromisoformat(r["f"]), dt.date.fromisoformat(r["t"])
        except (KeyError, ValueError):
            continue
        while d <= end:
            if d.weekday() < 5:
                days.add(d.isoformat())
            d += dt.timedelta(days=1)
    return days


def plan(mode: str, now: dt.datetime, cal: dict) -> tuple[bool, bool]:
    """(refresh_bills, refresh_votes)."""
    if mode == "full":
        return True, True
    if mode == "votes":
        return False, True
    if mode == "offline":
        return False, False
    local = now.astimezone(CT)
    today = local.date().isoformat()
    in_session = today in session_days(cal.get("house")) | session_days(cal.get("senate"))
    hour = local.hour
    votes = in_session and 8 <= hour <= 23
    bills = (in_session and hour in (6, 12, 18, 23)) or (not in_session and hour == 6)
    return bills, votes


# ---------------------------------------------------------------- merge + write

def merge(auto: dict | None, cur: dict | None) -> dict:
    b = dict(auto or {})
    cur = cur or {}
    for k, v in cur.items():
        if v in (None, "", [], {}):
            continue
        b[k] = v
    fns = dict(cur.get("fns") or {})
    if b.get("url"):
        fns.setdefault("cg", {"t": "Bill text, actions and cosponsors.", "src": "Congress.gov", "u": b["url"]})
    b["fns"] = fns
    b["auto"] = not bool(cur)
    return b


def load_json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def main() -> int:
    mode = os.environ.get("MODE", "auto").lower()
    now = dt.datetime.now(dt.timezone.utc)
    curated = load_json(CURATED, {"meta": {}, "bills": {}})
    meta = curated.get("meta") or {}
    prev = load_json(OUT, {})
    tracked = load_json(TRACKED, {"bills": [], "lastDiscovery": None})

    do_bills, do_votes = plan(mode, now, meta.get("calendar") or {})
    print(f"mode={mode} bills={do_bills} votes={do_votes}")

    congress, session = current_congress(now.astimezone(CT).date())
    auto_by_id = {b["id"]: b for b in prev.get("bills", []) if isinstance(b, dict) and b.get("id")}

    if do_bills:
        last = tracked.get("lastDiscovery")
        since = dt.datetime.fromisoformat(last) if last else now - dt.timedelta(days=2)
        since -= dt.timedelta(hours=1)
        for btype, num in discover(congress, since):
            bid = bill_id(congress, btype, num)
            if bid not in tracked["bills"]:
                tracked["bills"].append(bid)
        tracked["lastDiscovery"] = now.isoformat(timespec="seconds")

        wanted = {}
        for bid, c in (curated.get("bills") or {}).items():
            try:
                wanted[bid] = (int(c["congress"]), c["type"].lower(), int(c["number"]))
            except (KeyError, ValueError, AttributeError):
                warn(f"curated bill {bid} is missing congress/type/number")
        for bid in tracked["bills"]:
            m = re.match(r"^(\d+)-([a-z]+)(\d+)$", bid)
            if m and bid not in wanted:
                wanted[bid] = (int(m.group(1)), m.group(2), int(m.group(3)))
        curated_ids = set((curated.get("bills") or {}).keys())
        for bid, (c, t, n) in sorted(wanted.items()):
            try:
                fresh = fetch_bill(c, t, n)
            except Exception as e:  # noqa: BLE001
                warn(f"{bid}: {e}")
                continue
            if bid not in curated_ids and not fresh.get("strong"):
                # discovered but only committee-level activity: stop tracking
                auto_by_id.pop(bid, None)
                if bid in tracked["bills"]:
                    tracked["bills"].remove(bid)
                continue
            fresh["id"] = bid
            fresh["fetched"] = now.isoformat(timespec="seconds")
            auto_by_id[bid] = fresh

    bills = []
    ids = set(auto_by_id) | set((curated.get("bills") or {}).keys())
    for bid in sorted(ids):
        cur = (curated.get("bills") or {}).get(bid)
        auto = auto_by_id.get(bid)
        if not cur and bid not in tracked["bills"]:
            continue
        if auto and auto.get("auto") is not None:
            auto = {k: v for k, v in auto.items() if k not in ("auto",)}
        if auto:
            auto.pop("strong", None)
        b = merge(auto, cur)
        b["id"] = bid
        if b.get("congress") and b.get("congress") < congress and not b.get("reference") and b.get("auto"):
            b["reference"] = True
        bills.append(b)

    votes = prev.get("votes") or {"senate": [], "house": []}
    if do_votes:
        votes = {"senate": senate_with_backoff(congress, session, now, tracked, votes.get("senate") or []),
                 "house": house_votes(congress, session)}

    ledger = {
        "generatedAt": now.isoformat(timespec="seconds") if (do_bills or do_votes) else prev.get("generatedAt") or now.isoformat(timespec="seconds"),
        "congress": congress, "session": session,
        "meta": meta, "bills": bills, "votes": votes,
        "warnings": WARN[-20:],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    new = json.dumps(ledger, indent=1, ensure_ascii=False, sort_keys=True)
    old = OUT.read_text(encoding="utf-8") if OUT.exists() else ""

    # don't commit a new timestamp alone: compare without generatedAt
    def strip(s: str) -> str:
        return re.sub(r'"generatedAt": "[^"]*"', "", s)
    if strip(new) != strip(old):
        OUT.write_text(new + "\n", encoding="utf-8")
        print(f"wrote {OUT.relative_to(ROOT)}: {len(bills)} bills, {len(votes.get('senate', []))} Senate and {len(votes.get('house', []))} House votes")
    else:
        print("no data changes")
    if do_bills or do_votes:
        TRACKED.write_text(json.dumps(tracked, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
