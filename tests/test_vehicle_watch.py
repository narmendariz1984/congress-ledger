import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import vehicle_watch as W  # noqa: E402

# trimmed from the Senate floor logs, with the markup they use
PERIODICAL = """<html><head><style>.x{}</style><script>var a="legislative vehicle H.R. 9";</script></head><body>
<article><h2>Wednesday, September 30, 2026</h2>
<p>Leader Thune filed cloture on the motion to proceed to Cal. #453, H.R.2347, legislative vehicle for Permitting Reform.</p>
<p>Passed S.1234, Electric Vehicle Charging Act, by UC.</p></article>
<article><h2>Monday, November 16, 2026</h2><p>Cloture invoked on the Capito substitute amendment #6883 to H.R.2347: 70-27.</p>
<p>The bill would apply to U.S. 5 highway vehicles for freight.</p></article></body></html>"""
DAILY = """<div class="entry"><p><strong>Monday, November 9, 2026</strong></p>
<p>At 5:30 p.m., the Senate will vote on cloture on the motion to proceed to H.R.&nbsp;2347, the legislative vehicle for the permitting reform bill.</p>
<p>Also expected: H.J.Res. 140 as the vehicle for the continuing resolution.</p></div>"""
VEH = {"vehicles": [{"bill": "119-hr2347", "carries": "119-s5653"}]}


class Find(unittest.TestCase):
    def test_reads_the_floor_logs(self):
        a = W.find(W.text_of(PERIODICAL), date(2026, 11, 17))
        self.assertEqual([(h["id"], h["day"], h["for"]) for h in a], [("119-hr2347", "2026-09-30", "Permitting Reform")])
        b = W.find(W.text_of(DAILY), date(2026, 11, 17))
        self.assertEqual([(h["id"], h["num"], h["day"]) for h in b],
                         [("119-hr2347", "H.R. 2347", "2026-11-09"), ("119-hjres140", "H.J.Res. 140", "2026-11-09")])
        self.assertEqual(b[1]["for"], "continuing resolution")

    def test_not_cars_scripts_or_us_routes(self):
        found = {h["id"] for h in W.find(W.text_of(PERIODICAL), date(2026, 11, 17))}
        self.assertNotIn("119-s1234", found)
        self.assertNotIn("119-hr9", found)
        self.assertNotIn("119-s5", found)

    def test_congress_from_the_day(self):
        self.assertEqual(W.congress_of(date(2026, 11, 9)), 119)
        self.assertEqual(W.congress_of(date(2027, 1, 2)), 119)
        self.assertEqual(W.congress_of(date(2027, 1, 3)), 120)


class FakeGH:
    def __init__(self, issues=()):
        self.existing, self.opened, self.closed = list(issues), [], []

    def issues(self):
        return self.existing

    def ensure_label(self):
        pass

    def open(self, title, body):
        self.opened.append((title, body))

    def close(self, number, note):
        self.closed.append(number)


class Run(unittest.TestCase):
    def pages(self, url):
        return DAILY if "dailypress" in url else PERIODICAL

    def test_opens_one_issue_per_new_bill_and_skips_listed_vehicles(self):
        gh = FakeGH()
        done = W.run(fetch=self.pages, gh=gh, vehicles=VEH, today=date(2026, 11, 17), log=lambda *_: None)
        self.assertEqual([t for t, _ in gh.opened], ["Possible vehicle: H.J.Res. 140 (119th Congress)"])
        body = gh.opened[0][1]
        self.assertIn("as the vehicle for the continuing resolution", body)
        self.assertIn('"bill": "119-hjres140"', body)
        self.assertIn("https://www.dailypress.senate.gov/", body)
        self.assertEqual(done["opened"], ["H.J.Res. 140"])

    def test_never_reopens(self):
        gh = FakeGH([{"title": "Possible vehicle: H.J.Res. 140 (119th Congress)", "state": "closed", "number": 4}])
        done = W.run(fetch=self.pages, gh=gh, vehicles=VEH, today=date(2026, 11, 17), log=lambda *_: None)
        self.assertEqual((gh.opened, done["skipped"]), ([], ["H.J.Res. 140"]))

    def test_unlisted_bill_is_reported(self):
        gh = FakeGH()
        W.run(fetch=self.pages, gh=gh, vehicles={}, today=date(2026, 11, 17), log=lambda *_: None)
        self.assertIn("Possible vehicle: H.R. 2347 (119th Congress)", [t for t, _ in gh.opened])

    def test_one_page_failing_doesnt_stop_the_other(self):
        def fetch(url):
            if "periodical" in url:
                raise OSError("HTTP Error 403: Forbidden")
            return DAILY
        gh = FakeGH()
        done = W.run(fetch=fetch, gh=gh, vehicles=VEH, today=date(2026, 11, 17), log=lambda *_: None)
        self.assertEqual(done["opened"], ["H.J.Res. 140"])
        self.assertNotIn("outage", done)

    def test_cant_reach_note_opens_once_and_clears_itself(self):
        def down(url):
            raise OSError("HTTP Error 403: Forbidden")
        gh = FakeGH()
        self.assertEqual(W.run(fetch=down, gh=gh, vehicles=VEH, log=lambda *_: None)["outage"], "opened")
        self.assertEqual([t for t, _ in gh.opened], [W.OUTAGE_TITLE])
        gh2 = FakeGH([{"title": W.OUTAGE_TITLE, "state": "open", "number": 9}])
        self.assertNotIn("outage", W.run(fetch=down, gh=gh2, vehicles=VEH, log=lambda *_: None))
        self.assertEqual(gh2.opened, [])
        gh3 = FakeGH([{"title": W.OUTAGE_TITLE, "state": "open", "number": 9}])
        self.assertEqual(W.run(fetch=self.pages, gh=gh3, vehicles=VEH, today=date(2026, 11, 17), log=lambda *_: None)["outage"], "closed")
        self.assertEqual(gh3.closed, [9])

    def test_real_vehicles_file_is_known(self):
        import json
        v = json.loads((W.ROOT / "data" / "vehicles.json").read_text())
        self.assertIn("119-hr2347", W.known_ids(v))


if __name__ == "__main__":
    unittest.main()
