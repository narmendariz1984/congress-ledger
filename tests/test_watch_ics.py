"""Checks for the What to watch calendar (scripts/watch_ics.py). No network.

Run: python -m unittest discover -s tests -v
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import watch_ics as W  # noqa: E402

META = {"watchUpdated": "2026-11-05", "watch": [
    {"id": "funding", "date": "2026-12-11", "title": "Government funding runs out",
     "what": "Pass spending, or a shutdown starts; health care, too.", "src": [["STAT", "https://www.statnews.com/x"]]},
    {"id": "convenes", "date": "2027-01-03", "time": "12:00", "title": "120th Congress convenes", "what": "Noon Eastern."},
    {"id": "house-dem-leaders", "date": "2026-11-18", "end": "2026-11-19", "title": "House Democratic leadership elections"},
    {"id": "senate-dem-leader", "when": "Early December", "title": "Senate Democratic leadership election"},
]}


def unfold(text):
    return text.replace("\r\n ", "")


class WatchCalendar(unittest.TestCase):
    def setUp(self):
        self.text = W.build(META)

    def test_lines_are_crlf_and_at_most_75_octets(self):
        self.assertTrue(self.text.endswith("\r\n"))
        for line in self.text.split("\r\n"):
            self.assertLessEqual(len(line.encode()), 75, line)

    def test_only_dated_items_go_in_sorted_by_date(self):
        uids = [l for l in unfold(self.text).split("\r\n") if l.startswith("UID:")]
        self.assertEqual(uids, ["UID:house-dem-leaders@floorvotes.org", "UID:funding@floorvotes.org", "UID:convenes@floorvotes.org"])

    def test_all_day_end_is_the_next_day(self):
        t = unfold(self.text)
        self.assertIn("DTSTART;VALUE=DATE:20261211\r\nDTEND;VALUE=DATE:20261212", t)
        self.assertIn("DTSTART;VALUE=DATE:20261118\r\nDTEND;VALUE=DATE:20261120", t)  # two-day event

    def test_noon_eastern_in_january_is_17_utc(self):
        self.assertIn("DTSTART:20270103T170000Z", self.text)

    def test_text_is_escaped_and_links_back(self):
        t = unfold(self.text)
        self.assertIn("SUMMARY:120th Congress convenes", t)
        self.assertIn("Pass spending\\, or a shutdown starts\\; health care\\, too.", t)
        self.assertIn("URL:https://floorvotes.org/#w-funding", t)

    def test_same_input_same_output(self):
        self.assertEqual(self.text, W.build(META))

    def test_multibyte_characters_are_not_split(self):
        long = {"watch": [{"id": "x", "date": "2026-12-01", "title": "Ação " * 30}]}
        text = W.build(long)
        text.encode().decode()  # would raise if a character were cut in half
        self.assertIn("Ação Ação", unfold(text))

    def test_real_data_is_valid(self):
        meta = json.loads((ROOT / "data" / "curated.json").read_text(encoding="utf-8"))["meta"]
        for e in meta.get("watch") or []:
            self.assertTrue(e.get("id") and e.get("title") and (e.get("date") or e.get("when")), e)
            self.assertTrue(e.get("src"), f"{e['id']} has no source")
        W.build(meta)


if __name__ == "__main__":
    unittest.main()
