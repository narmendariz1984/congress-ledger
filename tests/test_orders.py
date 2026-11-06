"""Checks for scripts/orders.py (executive orders from the Federal Register). No network."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import orders as O  # noqa: E402

PAGE = {"count": 3, "next_page_url": None, "results": [
    {"executive_order_number": 14148, "title": "Initial Rescissions of Harmful Executive Orders and Actions",
     "signing_date": "2025-01-20", "publication_date": "2025-01-28", "citation": "90 FR 8237",
     "html_url": "https://www.federalregister.gov/d/2025-01901", "pdf_url": "https://x/1.pdf",
     "executive_order_notes": "Revokes: EO 13985, January 20, 2021; EO 13988, January 20, 2021\nAmended by: EO 14236, March 14, 2025"},
    {"executive_order_number": 14236, "title": "Additional Rescissions of Harmful Executive Orders and Actions",
     "signing_date": "2025-03-14", "publication_date": "2025-03-20", "citation": "90 FR 13037",
     "html_url": "https://www.federalregister.gov/d/2025-04866",
     "executive_order_notes": "Amends: EO 14148, January 20, 2025"},
    {"executive_order_number": 14200, "title": "A Temporary Order", "signing_date": "2025-02-10",
     "executive_order_notes": "See: EO 14148; Revoked by: Executive Order 14300"},
    {"executive_order_number": None, "title": "Not an order"},
]}


class Notes(unittest.TestCase):
    def test_a_label_covers_every_order_after_it(self):
        r = O.relations("Revokes: EO 13985, January 20, 2021; EO 13988, January 20, 2021\nAmended by: EO 14236, March 14, 2025")
        self.assertEqual(r, {"revokes": [13985, 13988], "amendedBy": [14236]})

    def test_labels_without_separators(self):
        # EO 14217's real notes: no semicolon or line break before "Amends" and "Amended by"
        r = O.relations("Revokes: Memo. of November 13, 1961; EO 13318, November 21, 2003 Amends: EO 13562, December 27, 2010 Amended by: EO 14410, June 3, 2026", 14217)
        self.assertEqual(r, {"revokes": [13318], "amends": [13562], "amendedBy": [14410]})

    def test_an_older_order_cannot_revoke_a_newer_one(self):
        self.assertEqual(O.relations("Revoked by: EO 14100; Revokes: EO 14500", 14200), {})

    def test_other_wordings(self):
        self.assertEqual(O.relations("See: EO 14148; Revoked by: Executive Order 14300"), {"see": [14148], "revokedBy": [14300]})
        self.assertEqual(O.relations("Supersedes: E.O. 14001"), {"supersedes": [14001]})
        self.assertEqual(O.relations(""), {})


class Fetch(unittest.TestCase):
    def setUp(self):
        self.old = O.get_json
        O.get_json = lambda url: PAGE

    def tearDown(self):
        O.get_json = self.old

    def test_orders_newest_first_without_junk(self):
        out = O.fetch_all()
        self.assertEqual([o["n"] for o in out], [14236, 14200, 14148])
        self.assertEqual(out[2]["c"], "90 FR 8237")

    def test_an_amending_order_marks_the_order_it_amends(self):
        out = {o["n"]: o for o in O.fetch_all()}
        self.assertIn(14236, out[14148]["rel"]["amendedBy"])
        self.assertEqual(out[14148]["rel"]["amendedBy"].count(14236), 1)  # listed in both notes, kept once
        self.assertEqual(out[14200]["rel"]["revokedBy"], [14300])

    def test_query_asks_for_this_term_only(self):
        q = O.query(1)
        self.assertIn("conditions%5Bpresident%5D%5B%5D=donald-trump", q)
        self.assertIn("conditions%5Bsigning_date%5D%5Bgte%5D=2025-01-20", q)
        self.assertIn("executive_order", q)


class Interval(unittest.TestCase):
    def test_unreachable_federal_register_keeps_the_last_file(self):
        with tempfile.TemporaryDirectory() as d:
            old = (O.OUT, O.STATE, O.get_json)
            O.OUT, O.STATE = Path(d) / "orders.json", Path(d) / "state.json"
            O.OUT.write_text('{"keep": true}')

            def down(url):
                raise TimeoutError("no route")
            O.get_json = down
            os.environ["FORCE"] = "1"
            try:
                self.assertEqual(O.main(), 0)
                self.assertEqual(O.OUT.read_text(), '{"keep": true}')
            finally:
                os.environ.pop("FORCE", None)
                O.OUT, O.STATE, O.get_json = old

    def test_writes_once_then_reports_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            old = (O.OUT, O.STATE, O.get_json)
            O.OUT, O.STATE = Path(d) / "orders.json", Path(d) / "state.json"
            O.get_json = lambda url: PAGE
            os.environ["FORCE"] = "1"
            try:
                O.main()
                first = O.OUT.read_text()
                O.main()
                self.assertEqual(O.OUT.read_text(), first)  # no new timestamp when nothing changed
                self.assertEqual(len(json.loads(first)["orders"]), 3)
            finally:
                os.environ.pop("FORCE", None)
                O.OUT, O.STATE, O.get_json = old


if __name__ == "__main__":
    unittest.main()
