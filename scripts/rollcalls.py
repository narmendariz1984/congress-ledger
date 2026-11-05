"""Every roll call of the current Congress, with each member's vote, from Voteview (UCLA).

Writes site/data/rollcalls.json. The site uses it for the full Votes tab, party splits,
crossover votes and how each state's members voted on bills that died.

Be gentle with Voteview: identifying User-Agent, at most one check every few hours, and a
conditional request on the small roll call lists first. The big member-vote files are only
downloaded when a roll call list has changed.

Run: python scripts/rollcalls.py            (respects the interval)
     FORCE=1 python scripts/rollcalls.py    (ignore the interval)
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "data" / "rollcalls.json"
STATE = ROOT / "data" / "rollcalls_state.json"
UA = "congress-ledger/1.0 (+https://github.com/narmendariz1984/congress-ledger)"
BASE = "https://voteview.com/static/data/out"
MIN_HOURS = 4
CONGRESS = int(os.environ.get("CONGRESS", "119"))
PARTY = {"100": "D", "200": "R"}
# Voteview cast codes: 1-3 yea (incl. paired, announced), 4-6 nay, 7-8 present, 9 not voting, 0 not a member
CAST = {"1": "Y", "2": "Y", "3": "Y", "4": "N", "5": "N", "6": "N", "7": "P", "8": "P", "9": "."}


def url(kind: str, ch: str) -> str:
    return f"{BASE}/{kind}/{ch}{CONGRESS}_{kind}.csv"


def get(u: str, since: str | None = None, timeout: int = 120) -> tuple[int, bytes, str | None]:
    """(status, body, last-modified). 304 means unchanged since `since`."""
    h = {"User-Agent": UA, "Accept": "text/csv,*/*"}
    if since:
        h["If-Modified-Since"] = since
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=h), timeout=timeout) as r:
                return r.status, r.read(), r.headers.get("Last-Modified")
        except urllib.error.HTTPError as e:
            if e.code == 304:
                return 304, b"", since
            if e.code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(10 * (attempt + 1))
                last = e
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            time.sleep(10 * (attempt + 1))
    raise last  # type: ignore[misc]


def rows(body: bytes) -> list[dict]:
    return list(csv.DictReader(io.StringIO(body.decode("utf-8-sig"))))


def num(x) -> int | None:
    try:
        return int(float(str(x).strip()))
    except ValueError:
        return None


def person_name(bioname: str) -> str:
    """Voteview's "McCARTHY, Kevin" or "CRUZ, Rafael Edward (Ted)" -> "Kevin McCarthy", "Ted Cruz"."""
    last, _, first = (bioname or "").partition(",")
    nick = re.search(r"\(([^)]+)\)", first)
    first = re.sub(r"\([^)]*\)", "", first)
    first = [w for w in re.split(r"[\s,]+", first.strip()) if w and not re.fullmatch(r"(Jr|Sr|II|III|IV)\.?", w)]
    given = nick.group(1).strip() if nick else (first[0] if first else "")

    def fix(piece: str) -> str:
        m = re.match(r"^([A-Z][a-z]+)([A-Z].*)$", piece)  # McCARTHY, DeLAURO: keep the mixed-case prefix
        if m:
            return m.group(1) + m.group(2).lower().capitalize()
        return piece[:1].upper() + piece[1:].lower()

    fam = re.sub(r"[A-Za-z]+", lambda m: fix(m.group(0)), last.strip())
    fam = re.sub(r"'([a-z])", lambda m: "'" + m.group(1).upper(), fam)  # O'Rourke
    return f"{given} {fam}".strip()


def build(ch: str, rc_rows: list[dict], mem_rows: list[dict], vote_rows: list[dict]) -> tuple[list, list]:
    """Members (in a fixed order) and roll calls, each with a vote string in that order."""
    chamber = "House" if ch == "H" else "Senate"
    members, index = [], {}
    for m in mem_rows:
        if (m.get("chamber") or chamber) != chamber or str(m.get("congress") or CONGRESS) != str(CONGRESS):
            continue
        icpsr = (m.get("icpsr") or "").strip()
        if not icpsr or icpsr in index:
            continue
        index[icpsr] = len(members)
        rec = {"id": int(icpsr), "n": person_name(m.get("bioname") or ""), "p": PARTY.get((m.get("party_code") or "").strip(), "I"),
               "s": (m.get("state_abbrev") or "").strip()}
        dist = num(m.get("district_code"))
        if ch == "H" and dist is not None:
            rec["d"] = dist
        members.append(rec)
    casts: dict[int, list[str]] = {}
    for v in vote_rows:
        if (v.get("chamber") or chamber) != chamber:
            continue
        r, i = num(v.get("rollnumber")), index.get((v.get("icpsr") or "").strip())
        if r is None or i is None:
            continue
        casts.setdefault(r, ["_"] * len(members))[i] = CAST.get((v.get("cast_code") or "").strip(), "_")
    votes = []
    for r in rc_rows:
        if (r.get("chamber") or chamber) != chamber:
            continue
        rn = num(r.get("rollnumber"))
        if rn is None:
            continue
        desc = re.sub(r"\s+", " ", html.unescape(r.get("vote_desc") or r.get("dtl_desc") or "")).strip()
        votes.append({
            "ch": ch, "r": rn, "n": num(r.get("clerk_rollnumber")) or rn, "sess": num(r.get("session")),
            "d": (r.get("date") or "").strip()[:10],
            "q": re.sub(r"\s+", " ", (r.get("vote_question") or "").strip()),
            "res": (r.get("vote_result") or "").strip(),
            "y": num(r.get("yea_count")) or 0, "no": num(r.get("nay_count")) or 0,
            "m": re.sub(r"\s+", "", (r.get("bill_number") or "").upper()),
            "t": desc[:300],
            "v": "".join(casts.get(rn, [])),
        })
    votes.sort(key=lambda x: (x["d"], x["r"]), reverse=True)
    return members, votes


def load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def main() -> int:
    now = dt.datetime.now(dt.timezone.utc)
    state = load(STATE, {})
    force = os.environ.get("FORCE") == "1" or not OUT.exists()
    if not force and state.get("lastCheck"):
        age = (now - dt.datetime.fromisoformat(state["lastCheck"])).total_seconds() / 3600
        if age < MIN_HOURS:
            print(f"roll calls: checked {age:.1f}h ago, next check after {MIN_HOURS}h")
            return 0
    mod = state.setdefault("lastModified", {})
    try:
        rc = {}
        changed = force
        for ch in ("H", "S"):
            u = url("rollcalls", ch)
            status, body, lm = get(u, None if force else mod.get(u))
            if status != 304:
                rc[ch], changed = rows(body), True
                if lm:
                    mod[u] = lm
        state["lastCheck"] = now.isoformat(timespec="seconds")
        if not changed:
            print("roll calls: Voteview unchanged since last check")
            STATE.write_text(json.dumps(state, indent=1) + "\n", encoding="utf-8")
            return 0
        out = {"congress": CONGRESS, "src": "Voteview (UCLA), voteview.com", "members": {}, "votes": []}
        for ch in ("H", "S"):
            if ch not in rc:
                rc[ch] = rows(get(url("rollcalls", ch))[1])
            mem = rows(get(url("members", ch))[1])
            vts = rows(get(url("votes", ch), timeout=300)[1])
            members, votes = build(ch, rc[ch], mem, vts)
            out["members"][ch] = members
            out["votes"] += votes
            print(f"roll calls: {ch} {len(votes)} roll calls, {len(members)} members")
        out["votes"].sort(key=lambda x: (x["d"], x["ch"], x["r"]), reverse=True)
        out["generatedAt"] = now.isoformat(timespec="seconds")
    except Exception as e:  # noqa: BLE001  keep the last good file
        print(f"::warning title=Roll calls::Voteview unavailable ({e.__class__.__name__}: {e}); keeping the last file")
        return 0
    if not out["votes"]:
        print("::warning title=Roll calls::Voteview returned no roll calls; keeping the last file")
        return 0
    text = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    OUT.write_text(text + "\n", encoding="utf-8")
    STATE.write_text(json.dumps(state, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(text) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
