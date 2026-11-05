"""Backend checks: keep rule, roll call discovery, House vote details, Senate votes.

Run: python -m unittest discover -s tests -v
No network: every call to Congress.gov or Voteview is replaced with sample data.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fetch as F  # noqa: E402


def acts(*texts):
    return [{"text": t} for t in texts]


class Patch:
    """Swap module attributes for one test, then put them back."""

    def __init__(self, **kw):
        self.kw, self.old = kw, {}

    def __enter__(self):
        for k, v in self.kw.items():
            self.old[k] = getattr(F, k)
            setattr(F, k, v)

    def __exit__(self, *exc):
        for k, v in self.old.items():
            setattr(F, k, v)


class KeepRule(unittest.TestCase):
    def kept(self, *texts):
        return F.derive(acts(*texts), [])["strong"]

    def test_law_is_kept(self):
        self.assertTrue(self.kept("Became Public Law No: 119-12."))

    def test_voice_vote_passage_is_dropped(self):
        self.assertFalse(self.kept(
            "Passed/agreed to in House: On motion to suspend the rules and pass the bill, as amended Agreed to by voice vote.",
            "Received in the Senate and Read twice and referred to the Committee on Finance."))

    def test_unanimous_consent_passage_is_dropped(self):
        self.assertFalse(self.kept("Passed Senate without amendment by Unanimous Consent."))

    def test_roll_call_passage_is_kept(self):
        self.assertTrue(self.kept(
            "Passed/agreed to in House: On motion to suspend the rules and pass the bill, as amended Agreed to by the Yeas and Nays: (2/3 required): 410 - 1 (Roll no. 215)."))

    def test_failed_motion_to_proceed_is_kept(self):
        # S.J.Res. 197, 48-51
        self.assertTrue(self.kept(
            "Motion to proceed to consideration of measure rejected in Senate by Yea-Nay Vote. 48 - 51. Record Vote Number: 268."))

    def test_failed_cloture_is_kept(self):
        self.assertTrue(self.kept(
            "Cloture on the motion to proceed to the measure not invoked in Senate by Yea-Nay Vote. 51 - 48. Record Vote Number: 400."))

    def test_committee_discharge_housekeeping_is_not_a_fight(self):
        # S. 675: committee discharged by unanimous consent
        self.assertFalse(self.kept(
            "Passed Senate with an amendment by Unanimous Consent.",
            "Senate Committee on Energy and Natural Resources discharged by Unanimous Consent."))

    def test_discharge_motion_is_kept(self):
        self.assertTrue(self.kept("Table Motion to Discharge Agreed to by the Yeas and Nays: 200 - 198 (Roll no. 265)."))

    def test_committee_only_is_dropped(self):
        self.assertFalse(self.kept("Reported by the Committee on Energy.", "Placed on the Union Calendar, Calendar No. 412."))


class KilledStatus(unittest.TestCase):
    """Killed = the latest decisive floor vote failed and nothing moved the bill since.
    Actions are newest first, as Congress.gov returns them."""

    def check(self, want, *texts):
        self.assertEqual(F.killed(acts(*texts)), want, texts[0][:60])

    def test_failed_cloture_after_house_passage(self):
        self.check(True, "Cloture on the motion to proceed to the measure not invoked in Senate by Yea-Nay Vote. 51 - 48. Record Vote Number: 400.",
                   "Passed/agreed to in House: On passage Passed by the Yeas and Nays: 216 - 214 (Roll no. 145).")
        self.assertEqual(F.derive(acts("Cloture on the motion to proceed to the measure not invoked in Senate by Yea-Nay Vote. 51 - 48.",
                                       "Passed/agreed to in House: On passage Passed by the Yeas and Nays: 216 - 214 (Roll no. 145)."), [])["status"], "killed")

    def test_reconsider_motion_is_not_a_revival(self):
        self.check(True, "Motion by Senator Thune to reconsider the vote by which cloture on the motion to proceed to S. 12 was not invoked (Record Vote No. 300) entered in Senate.",
                   "Cloture on the motion to proceed to the measure not invoked in Senate by Yea-Nay Vote. 51 - 48. Record Vote Number: 300.")

    def test_later_passage_revives(self):
        self.check(False, "Passed Senate without amendment by Yea-Nay Vote. 60 - 38.",
                   "Cloture on the motion to proceed to the measure invoked in Senate by Yea-Nay Vote. 61 - 37.",
                   "Cloture on the motion to proceed to the measure not invoked in Senate by Yea-Nay Vote. 55 - 45.")
        self.check(False, "Passed/agreed to in House: On passage Passed by the Yeas and Nays: 230 - 190 (Roll no. 40).",
                   "On motion to suspend the rules and pass the bill Failed by the Yeas and Nays: (2/3 required): 250 - 170 (Roll no. 9).")

    def test_routine_failures_are_not_kills(self):
        self.check(False, "On motion to recommit Failed by the Yeas and Nays: 210 - 220 (Roll no. 98).", "Rule H. Res. 5 passed House.")
        self.check(False, "Amendment SA 12 not agreed to in Senate by Yea-Nay Vote. 45 - 55.")
        self.check(False, "On motion that the House instruct conferees Failed by the Yeas and Nays: 200 - 210 (Roll no. 3).")

    def test_each_kill_wording(self):
        for t in ("Failed of passage/not agreed to in House On motion to suspend the rules and pass the bill Failed by the Yeas and Nays: (2/3 required): 250 - 170 (Roll no. 9).",
                  "Motion to discharge Senate Committee on Foreign Relations rejected by Yea-Nay Vote. 47 - 52. Record Vote Number: 210.",
                  "Motion to proceed to consideration of measure rejected in Senate by Yea-Nay Vote. 48 - 51. Record Vote Number: 268.",
                  "Rule H. Res. 600 failed passage of House.",
                  "Table Motion to Discharge Agreed to by the Yeas and Nays: 200 - 198 (Roll no. 265).",
                  "Failed of passage in Senate by Yea-Nay Vote. 45 - 55. Record Vote Number: 50."):
            self.check(True, t)

    def test_veto_outranks_killed(self):
        self.assertEqual(F.derive(acts("On passage, the objections of the President to the contrary notwithstanding Failed by the Yeas and Nays: (2/3 required): 212 - 206 (Roll no. 9).",
                                       "Vetoed by President."), [])["status"], "vetoed")

    def test_timeline_marks_only_real_kills(self):
        ev = F.timeline_from([{"actionDate": "2026-01-01", "text": "On motion to recommit Failed by the Yeas and Nays: 210 - 220 (Roll no. 98)."},
                              {"actionDate": "2026-01-02", "text": "Cloture on the motion to proceed to the measure not invoked in Senate by Yea-Nay Vote. 51 - 48."}])
        self.assertEqual([e.get("k") for e in ev], [None, "kill"])


class RollCallDiscovery(unittest.TestCase):
    def test_finds_bills_and_skips_nominations_and_simple_resolutions(self):
        pages = {
            ("house-vote/119/1", 0): {"houseRollCallVotes": [
                {"legislationType": "HR", "legislationNumber": "131"},     # H.R. 131, failed veto override
                {"legislationType": "HRES", "legislationNumber": "5"},     # simple resolution: skip
                {"legislationType": "HJRES", "legislationNumber": "210"}]},
            ("house-vote/119/2", 0): {"houseRollCallVotes": []},
        }
        csv_text = ("congress,chamber,rollnumber,date,session,clerk_rollnumber,bill_number\n"
                    "119,Senate,1,2025-01-09,1,1,S5\n"
                    "119,Senate,2,2025-02-01,1,2,PN12\n"        # nomination: skip
                    "119,Senate,3,2025-03-01,1,3,SJRES197\n")
        with Patch(api=lambda path, **kw: pages.get((path, kw.get("offset", 0)), {"x": []}),
                   _get=lambda url, timeout=30: csv_text.encode()):
            found = F.rollcall_bills(119)
        self.assertEqual(found, {"119-hr131", "119-hjres210", "119-s5", "119-sjres197"})

    def test_failure_returns_none_not_a_partial_list(self):
        def boom(*a, **k):
            raise TimeoutError()
        with Patch(api=boom):
            self.assertIsNone(F.rollcall_bills(119))


class HouseVoteDetail(unittest.TestCase):
    def test_party_totals_are_summed(self):
        page = {"houseRollCallVote": {"voteQuestion": "On Motion to Suspend the Rules and Pass",
                                      "votePartyTotal": [{"voteParty": "R", "yeaTotal": 200, "nayTotal": 10},
                                                         {"voteParty": "D", "yeaTotal": 12, "nayTotal": 196}]}}
        with Patch(api=lambda path, **kw: page):
            self.assertEqual(F.house_vote_detail(119, 2, 9),
                             {"q": "On Motion to Suspend the Rules and Pass", "y": "212", "n": "206"})

    def test_flat_totals(self):
        with Patch(api=lambda path, **kw: {"vote": {"question": "On Passage", "yeaTotal": "230", "nayTotal": "190"}}):
            self.assertEqual(F.house_vote_detail(119, 2, 9), {"q": "On Passage", "y": "230", "n": "190"})

    def test_nothing_usable_is_none(self):
        with Patch(api=lambda path, **kw: {"vote": {}}):
            self.assertIsNone(F.house_vote_detail(119, 2, 9))


class SenateVotes(unittest.TestCase):
    def test_full_title_and_decoded_entities(self):
        long_desc = ("A joint resolution providing for congressional disapproval under chapter 8 of title 5, "
                     "United States Code, of the rule submitted by the Centers for Medicare &#38; Medicaid Services "
                     "of the Department of Health and Human Services relating to \"Medicare Program\".")
        csv_text = ("congress,chamber,rollnumber,date,session,clerk_rollnumber,yea_count,nay_count,bill_number,vote_result,vote_desc,vote_question\n"
                    '119,Senate,700,2026-09-29,2,268,48,51,SJRES197,Motion to Proceed Rejected,"'
                    + long_desc.replace('"', '""') + '",On the Motion to Proceed\n')   # CSV doubles inner quotes
        with Patch(_get=lambda url, timeout=30: csv_text.encode()):
            v = F.senate_votes(119, 2)[0]
        self.assertIn("Medicare & Medicaid", v["title"])
        self.assertNotIn("&#38;", v["title"])
        self.assertTrue(v["title"].endswith('"Medicare Program".'))   # not cut at 200 characters
        self.assertEqual((v["y"], v["n_"], v["n"]), ("48", "51", 268))


if __name__ == "__main__":
    unittest.main()
