"""Executive orders of the current presidential term, from the Federal Register API.

Writes site/data/orders.json for the site's Executive orders tab. The Federal Register is
the official journal of the U.S. government; its API is public and needs no key.

Be gentle: identifying User-Agent, at most one check every 6 hours.
Run: python scripts/orders.py          (respects the interval)
     FORCE=1 python scripts/orders.py  (ignore the interval)
"""
from __future__ import annotations

import datetime as dt
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
OUT = ROOT / "site" / "data" / "orders.json"
STATE = ROOT / "data" / "orders_state.json"
UA = "congress-ledger/1.0 (+https://github.com/narmendariz1984/congress-ledger)"
API = "https://www.federalregister.gov/api/v1/documents.json"
MIN_HOURS = 6
PRESIDENT = os.environ.get("EO_PRESIDENT", "donald-trump")
TERM_START = os.environ.get("EO_TERM_START", "2025-01-20")
FIELDS = ["executive_order_number", "title", "signing_date", "publication_date", "citation",
          "document_number", "html_url", "pdf_url", "executive_order_notes", "abstract"]


def query(page: int) -> str:
    q = [("conditions[type][]", "PRESDOCU"),
         ("conditions[presidential_document_type][]", "executive_order"),
         ("conditions[president][]", PRESIDENT),
         ("conditions[signing_date][gte]", TERM_START),
         ("conditions[correction]", "0"),
         ("order", "executive_order_number"),
         ("per_page", "200"), ("page", str(page))] + [("fields[]", f) for f in FIELDS]
    return API + "?" + urllib.parse.urlencode(q)


def get_json(url: str) -> dict:
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(10 * (attempt + 1))
                last = e
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            time.sleep(10 * (attempt + 1))
    raise last  # type: ignore[misc]


EO_REF = re.compile(r"\b(?:EO|E\.O\.|Executive Order)\s*(\d{4,5})", re.I)


def relations(notes: str) -> dict:
    """Read the Federal Register's notes: "Revokes: EO 14148; See: EO 14189; Revoked by: EO 14200"."""
    out: dict[str, list[int]] = {}
    key = None  # a label ("Revokes:") covers the items after it until the next label
    for part in re.split(r";|\n", notes or ""):
        m = re.match(r"\s*([A-Za-z][A-Za-z ,]*?)\s*:\s*(.*)", part)
        if m and not EO_REF.match(m.group(1)):
            label = m.group(1).strip().lower()
            key = ("revokedBy" if "revoked by" in label else "amendedBy" if "amended by" in label
                   else "supersededBy" if "superseded by" in label else "revokes" if "revoke" in label
                   else "amends" if "amend" in label else "supersedes" if "supersede" in label else "see")
            part = m.group(2)
        if not key:
            continue
        nums = [int(n) for n in EO_REF.findall(part)]
        if nums:
            out.setdefault(key, [])
            out[key] += [n for n in nums if n not in out[key]]
    return out


def tidy(o: dict) -> dict | None:
    num = o.get("executive_order_number")
    try:
        num = int(num)
    except (TypeError, ValueError):
        return None
    notes = re.sub(r"\s+", " ", o.get("executive_order_notes") or "").strip()
    rec = {"n": num, "t": re.sub(r"\s+", " ", (o.get("title") or "").strip()),
           "s": o.get("signing_date") or "", "p": o.get("publication_date") or "",
           "c": o.get("citation") or "", "u": o.get("html_url") or "", "pdf": o.get("pdf_url") or ""}
    if notes:
        rec["notes"] = notes
        rel = relations(notes)
        if rel:
            rec["rel"] = rel
    ab = re.sub(r"\s+", " ", o.get("abstract") or "").strip()
    if ab:
        rec["a"] = ab[:400]
    return rec


def fetch_all() -> list[dict]:
    out, page = [], 1
    while page <= 20:
        data = get_json(query(page))
        out += [r for r in (tidy(o) for o in data.get("results") or []) if r]
        if not data.get("next_page_url"):
            break
        page += 1
    # orders that revoke or amend a later one: mark the target too, so its status is right
    by = {o["n"]: o for o in out}
    for o in out:
        for key, back in (("revokes", "revokedBy"), ("amends", "amendedBy"), ("supersedes", "supersededBy")):
            for n in (o.get("rel") or {}).get(key, []):
                t = by.get(n)
                if t is not None:
                    lst = t.setdefault("rel", {}).setdefault(back, [])
                    if o["n"] not in lst:
                        lst.append(o["n"])
    out.sort(key=lambda o: o["n"], reverse=True)
    return out


def main() -> int:
    now = dt.datetime.now(dt.timezone.utc)
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    force = os.environ.get("FORCE") == "1" or not OUT.exists()
    if not force and state.get("lastCheck"):
        age = (now - dt.datetime.fromisoformat(state["lastCheck"])).total_seconds() / 3600
        if age < MIN_HOURS:
            print(f"executive orders: checked {age:.1f}h ago, next check after {MIN_HOURS}h")
            return 0
    try:
        orders = fetch_all()
    except Exception as e:  # noqa: BLE001  keep the last good file
        print(f"::warning title=Executive orders::Federal Register unavailable ({e.__class__.__name__}: {e}); keeping the last file")
        return 0
    state["lastCheck"] = now.isoformat(timespec="seconds")
    STATE.write_text(json.dumps(state, indent=1) + "\n", encoding="utf-8")
    if not orders:
        print("::warning title=Executive orders::the Federal Register returned no orders; keeping the last file")
        return 0
    body = {"president": PRESIDENT, "termStart": TERM_START,
            "src": "Federal Register (federalregister.gov)", "orders": orders}
    old = None
    try:
        old = json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    if old and {k: v for k, v in old.items() if k != "generatedAt"} == body:
        print(f"executive orders: unchanged ({len(orders)})")
        return 0
    body["generatedAt"] = now.isoformat(timespec="seconds")
    OUT.write_text(json.dumps(body, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {OUT.name}: {len(orders)} executive orders, EO {orders[-1]['n']} to {orders[0]['n']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
