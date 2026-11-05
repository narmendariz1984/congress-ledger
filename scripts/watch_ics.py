"""Build site/watch.ics, the "What to watch" calendar, from data/curated.json (meta.watch).

People subscribe to https://floorvotes.org/watch.ics, so editing a date in curated.json
reaches their calendars on the next refresh. Only dated items go in; items with just a
"when" (like "Early December") stay on the page until a date is set.

Output is the same for the same input (no clock reads), so it only changes the site
when the dates change. Run: python scripts/watch_ics.py
"""
import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CURATED = ROOT / "data" / "curated.json"
OUT = ROOT / "site" / "watch.ics"
SITE = "https://floorvotes.org"
ET = ZoneInfo("America/New_York")


def esc(s: str) -> str:
    return (s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
             .replace("\r\n", "\\n").replace("\n", "\\n"))


def fold(line: str) -> str:
    """RFC 5545: lines over 75 octets continue on the next line after a space."""
    out, cur = [], b""
    for ch in line:
        b = ch.encode()
        if len(cur) + len(b) > (75 if not out else 74):
            out.append(cur.decode())
            cur = b""
        cur += b
    out.append(cur.decode())
    return "\r\n ".join(out)


def ymd(d: str) -> str:
    return dt.date.fromisoformat(d).strftime("%Y%m%d")


def event_lines(e: dict, stamp: str) -> list[str]:
    d = dt.date.fromisoformat(e["date"])
    lines = ["BEGIN:VEVENT", f"UID:{e['id']}@floorvotes.org", f"DTSTAMP:{stamp}"]
    if e.get("time"):
        h, m = map(int, e["time"].split(":"))
        start = dt.datetime(d.year, d.month, d.day, h, m, tzinfo=ET).astimezone(dt.timezone.utc)
        end = start + dt.timedelta(hours=1)
        lines += [f"DTSTART:{start:%Y%m%dT%H%M%SZ}", f"DTEND:{end:%Y%m%dT%H%M%SZ}"]
    else:
        last = dt.date.fromisoformat(e.get("end") or e["date"])
        lines += [f"DTSTART;VALUE=DATE:{d:%Y%m%d}",
                  f"DTEND;VALUE=DATE:{last + dt.timedelta(days=1):%Y%m%d}",  # end is exclusive
                  "TRANSP:TRANSPARENT"]  # all-day notes shouldn't mark anyone busy
    url = f"{SITE}/#w-{e['id']}"
    desc = e.get("what", "")
    if e.get("src"):
        desc += "\n\nSources:\n" + "\n".join(f"{t}: {u}" for t, u in e["src"])
    desc += f"\n\nMore: {url}"
    lines += [f"SUMMARY:{esc(e['title'])}", f"DESCRIPTION:{esc(desc)}", f"URL:{url}",
              f"SEQUENCE:{int(e.get('seq', 0))}",
              f"STATUS:{'TENTATIVE' if e.get('tentative') else 'CONFIRMED'}", "END:VEVENT"]
    return lines


def build(meta: dict) -> str:
    updated = meta.get("watchUpdated") or "2026-01-01"
    stamp = f"{ymd(updated)}T000000Z"
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//floorvotes.org//What to watch//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             "X-WR-CALNAME:Congress: what to watch",
             "X-WR-CALDESC:" + esc("Deadlines and key dates in Congress, from floorvotes.org. Updates when dates change."),
             "X-WR-TIMEZONE:America/New_York",
             "REFRESH-INTERVAL;VALUE=DURATION:PT12H", "X-PUBLISHED-TTL:PT12H"]
    for e in sorted((e for e in meta.get("watch") or [] if e.get("date")), key=lambda e: (e["date"], e.get("time", ""))):
        lines += event_lines(e, stamp)
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(l) for l in lines) + "\r\n"


def main() -> int:
    meta = json.loads(CURATED.read_text(encoding="utf-8")).get("meta") or {}
    text = build(meta)
    if not OUT.exists() or OUT.read_bytes() != text.encode():
        OUT.write_bytes(text.encode())
        print(f"wrote {OUT.relative_to(ROOT)} ({text.count('BEGIN:VEVENT')} events)")
    else:
        print("watch.ics unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
