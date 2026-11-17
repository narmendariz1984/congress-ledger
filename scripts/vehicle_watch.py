"""Watch the Senate press galleries' floor logs for bills named as a "legislative vehicle"
and open a GitHub issue for each new one, for a person to review.

It never edits data/vehicles.json or the site: a vehicle only shows on floorvotes.org after
someone checks which bill it carries and adds the entry by hand. Congress.gov doesn't mark
these swaps, but the floor logs say so in plain words ("Cal. #453, H.R.2347, legislative
vehicle for Permitting Reform").

Runs on its own schedule (.github/workflows/vehicle-watch.yml), apart from the data refresh,
so a problem here can't touch the site. Polite: identifying User-Agent, two pages per run.
If neither page can be read, it opens one "can't reach" issue and closes it on its own once
a later run gets through.

Standard library only. Needs GITHUB_TOKEN (issues: write) and GITHUB_REPOSITORY.
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = "congress-ledger/1.0 (+https://github.com/narmendariz1984/congress-ledger)"
SOURCES = {
    "Senate Periodical Press Gallery": "https://www.periodicalpress.senate.gov/",
    "Senate Daily Press": "https://www.dailypress.senate.gov/",
}
LABEL = "vehicle-watch"
OUTAGE_TITLE = "Vehicle watcher can't reach the Senate floor logs"

# "legislative vehicle", "the vehicle for", "as a vehicle"; not cars ("electric vehicle")
VEHICLE = re.compile(r"\blegislative vehicles?\b|\b(?:the|a|as)\s+vehicles?\s+(?:for|to carry)\b", re.I)
CARS = re.compile(r"\b(?:electric|motor|autonomous|commercial|military|unmanned|off-highway|recreational)\s+vehicles?\b", re.I)
# H.R.2347, H.R. 2347, S.5653, H.J.Res. 7, S.Con.Res. 3; not "S. 5" inside "U.S. 5"
BILL = re.compile(r"(?<![A-Za-z.])(H\.\s?R\.|S\.|H\.\s?J\.\s?Res\.|S\.\s?J\.\s?Res\.|H\.\s?Con\.\s?Res\.|S\.\s?Con\.\s?Res\.|H\.\s?Res\.|S\.\s?Res\.)\s?(\d{1,5})\b")
TYPE = {"hr": "hr", "s": "s", "hjres": "hjres", "sjres": "sjres", "hconres": "hconres", "sconres": "sconres", "hres": "hres", "sres": "sres"}
NUM = {"hr": "H.R.", "s": "S.", "hjres": "H.J.Res.", "sjres": "S.J.Res.", "hconres": "H.Con.Res.", "sconres": "S.Con.Res.", "hres": "H.Res.", "sres": "S.Res."}
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
DAY = re.compile(rf"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+({MONTHS})\s+(\d{{1,2}}),?\s+(\d{{4}})\b")


def congress_of(d: date) -> int:
    """The Congress in session on a day (a new one starts Jan 3 of odd years)."""
    y = d.year - (1 if d.year % 2 == 1 and (d.month, d.day) < (1, 3) else 0)
    return (y - 1789) // 2 + 1


def text_of(page: str) -> list[str]:
    """A page's readable lines: scripts and styles dropped, one line per block element."""
    page = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", page)
    page = re.sub(r"(?i)<br\s*/?>|</?(p|div|li|ul|ol|h[1-6]|tr|td|article|section|header|footer|blockquote)\b[^>]*>", "\n", page)
    page = html.unescape(re.sub(r"<[^>]+>", " ", page))
    return [re.sub(r"[ \t ]+", " ", ln).strip() for ln in page.split("\n") if ln.strip()]


def find(lines: list[str], today: date) -> list[dict]:
    """Bills named as a vehicle, each with the line it was in and the day heading above it."""
    out, seen, day = [], set(), None
    for ln in lines:
        m = DAY.search(ln)
        if m:
            try:
                day = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%B %d %Y").date()
            except ValueError:
                pass
        if not VEHICLE.search(ln) or CARS.search(ln) and not re.search(r"legislative vehicle", ln, re.I):
            continue
        for b in BILL.finditer(ln):
            t = TYPE.get(re.sub(r"[^a-z]", "", b.group(1).lower()))
            if not t:
                continue
            c = congress_of(day or today)
            bid = f"{c}-{t}{int(b.group(2))}"
            if bid in seen:
                continue
            seen.add(bid)
            hint = re.search(r"vehicle\s+for\s+(?:the\s+)?([^.;()]{3,80})", ln[b.end():], re.I)
            out.append({"id": bid, "num": f"{NUM[t]} {int(b.group(2))}", "congress": c,
                        "day": (day or today).isoformat(), "line": ln[:600],
                        "for": hint.group(1).strip(" ,") if hint else ""})
    return out


def known_ids(vehicles: dict) -> set[str]:
    """Bills already handled: listed vehicles and the bills they carry."""
    ids = set()
    for e in (vehicles or {}).get("vehicles") or []:
        ids.update(x for x in (e.get("bill"), e.get("carries")) if x)
    return ids


def issue_title(hit: dict) -> str:
    return f"Possible vehicle: {hit['num']} ({hit['congress']}th Congress)"


def issue_body(hit: dict, src: str, url: str) -> str:
    entry = {"bill": hit["id"], "carries": f"{hit['congress']}-s0000 <- the bill it carries",
             "label": hit["for"] or "<the carried bill's name>", "since": hit["day"], "source": url}
    return "\n".join([
        f"The {src} floor log names **{hit['num']}** as a vehicle ({hit['day']}):",
        "", f"> {hit['line']}", "", f"Source: {url}", "",
        "If it's carrying another bill's text, find that bill on Congress.gov and add this to "
        "`data/vehicles.json` (fill in `carries` and `label`):", "",
        "```json", json.dumps(entry, indent=1), "```", "",
        "Close this issue if it isn't a swap. This watcher never edits the site or that file; "
        "it won't open this issue again either way.",
    ])


class GitHub:
    def __init__(self, repo: str, token: str):
        self.base, self.token = f"https://api.github.com/repos/{repo}", token

    def call(self, method: str, path: str, body: dict | None = None):
        req = urllib.request.Request(self.base + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
                                              "User-Agent": UA, "X-GitHub-Api-Version": "2022-11-28"})
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else None

    def issues(self) -> list[dict]:
        out = []
        for page in range(1, 6):
            got = self.call("GET", f"/issues?state=all&labels={LABEL}&per_page=100&page={page}") or []
            out += got
            if len(got) < 100:
                break
        return out

    def ensure_label(self):
        try:
            self.call("POST", "/labels", {"name": LABEL, "color": "b60205", "description": "Possible vehicle swap found in a Senate floor log"})
        except urllib.error.HTTPError as e:
            if e.code != 422:  # 422: already exists
                raise

    def open(self, title: str, body: str):
        return self.call("POST", "/issues", {"title": title, "body": body, "labels": [LABEL]})

    def close(self, number: int, note: str):
        self.call("POST", f"/issues/{number}/comments", {"body": note})
        self.call("PATCH", f"/issues/{number}", {"state": "closed"})


def get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def run(fetch=get, gh=None, vehicles=None, today=None, log=print) -> dict:
    """One check. Returns what it did, for the job summary and tests."""
    today = today or datetime.now(timezone.utc).date()
    known = known_ids(vehicles)
    hits, failed = [], []
    for src, url in SOURCES.items():
        try:
            for h in find(text_of(fetch(url)), today):
                hits.append((h, src, url))
        except Exception as e:  # noqa: BLE001  one page failing never stops the other
            failed.append(f"{src}: {e}")
            log(f"::warning::{src} couldn't be read: {e}")
    new = [(h, s, u) for h, s, u in hits if h["id"] not in known]
    done = {"found": [h["num"] for h, _, _ in hits], "opened": [], "skipped": [], "failed": failed}
    if gh is None:
        return done
    existing = gh.issues()
    titles = {i.get("title") for i in existing}
    if new:
        gh.ensure_label()
    for h, src, url in new:
        t = issue_title(h)
        if t in titles:
            done["skipped"].append(h["num"])
            continue
        gh.open(t, issue_body(h, src, url))
        titles.add(t)
        done["opened"].append(h["num"])
    # can't-reach note: one open issue while every page fails, closed once one works again
    outage = [i for i in existing if i.get("title") == OUTAGE_TITLE and i.get("state") == "open"]
    if len(failed) == len(SOURCES) and not outage:
        gh.ensure_label()
        gh.open(OUTAGE_TITLE, "Neither Senate floor log could be read on this run:\n\n" + "\n".join(f"- {f}" for f in failed)
                + "\n\nThe site isn't affected. This closes on its own once a later run reads one of them.")
        done["outage"] = "opened"
    elif len(failed) < len(SOURCES) and outage:
        for i in outage:
            gh.close(i["number"], "A floor log was read again, so the watcher is working.")
        done["outage"] = "closed"
    return done


def main() -> int:
    vehicles = json.loads((ROOT / "data" / "vehicles.json").read_text(encoding="utf-8"))
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    gh = GitHub(repo, token) if token and repo else None
    try:
        done = run(gh=gh, vehicles=vehicles)
    except Exception as e:  # noqa: BLE001  GitHub's API failing: report, don't fail the job
        print(f"::warning::vehicle watch stopped: {e}")
        return 0
    lines = [f"Found: {', '.join(done['found']) or 'nothing named as a vehicle'}",
             f"New issues: {', '.join(done['opened']) or 'none'}"]
    if done["skipped"]:
        lines.append(f"Already reported: {', '.join(done['skipped'])}")
    if done["failed"]:
        lines.append("Couldn't read: " + "; ".join(done["failed"]))
    print("\n".join(lines))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write("## Vehicle watch\n\n" + "\n".join(f"- {x}" for x in lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
