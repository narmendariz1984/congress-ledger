"""Backend checks: keep rule, roll call discovery, House vote details, Senate votes.

Run: python -m unittest discover -s tests -v
No network: every call to Congress.gov or Voteview is replaced with sample data.
"""
import json
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

    def test_senate_bringing_it_back_up_is_not_killed(self):
        # H.R. 4016 and S. 4784: cloture failed, then leaders moved to proceed again
        self.check(False, "Motion to proceed to consideration of measure made in Senate. (CR S8522)",
                   "Cloture on the motion to proceed to the measure not invoked in Senate by Yea-Nay Vote. 50 - 44. Record Vote Number: 575.")
        self.check(False, "Cloture motion on the motion to proceed to the measure presented in Senate.",
                   "Cloture on the motion to proceed to the measure not invoked in Senate by Yea-Nay Vote. 50 - 44.")
        # H.R. 3633: the motion to proceed came first, then cloture failed and only a reconsider was entered
        self.check(True, "Motion by Senator Tillis to reconsider the vote by which cloture on the motion to proceed to the measure was not invoked (Record Vote No. 234) entered in Senate.",
                   "Cloture on the motion to proceed to the measure not invoked in Senate by Yea-Nay Vote. 49 - 50. Record Vote Number: 234.",
                   "Motion to proceed to consideration of measure made in Senate. (CR S4557)",
                   "Cloture motion on the motion to proceed to the measure presented in Senate. (CR S4557)")

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

    def test_timeline_skips_votes_on_reconsidering_and_page_ranges(self):
        ev = F.timeline_from([
            {"actionDate": "2025-10-08", "text": "Motion to proceed to consideration of the motion to reconsider the vote by which the second cloture on the motion to proceed to the S. 2882 was not invoked (Record Vote No. 544) agreed to in Senate by Yea-Nay Vote. 52 - 47."},
            {"actionDate": "2026-07-23", "text": "Motion to proceed to consideration of measure made in Senate. (CR S4241-4242)"}])
        self.assertEqual([e.get("k") for e in ev], [None, None])
        self.assertEqual([e.get("v") for e in ev], ["52–47", None])


class CommitsOnlyOnDataChange(unittest.TestCase):
    def test_only_a_new_timestamp_is_not_a_change(self):
        old = '{"generatedAt": "2026-11-07T10:00:00+00:00", "bills": [1]}'
        self.assertFalse(F.data_changed('{"generatedAt": "2026-11-07T11:00:00+00:00", "bills": [1]}', old))
        self.assertTrue(F.data_changed('{"generatedAt": "2026-11-07T11:00:00+00:00", "bills": [2]}', old))
        # outage warnings alone aren't a data change either
        self.assertFalse(F.data_changed('{"generatedAt": "x", "bills": [1], "warnings": ["119-hjres104: timed out"]}', old))
        self.assertTrue(F.data_changed("not json", old))


class OutageBreaker(unittest.TestCase):
    def test_trips_after_three_failures_in_a_row(self):
        b = F.Breaker(3)
        b.fail("a"); b.fail("b"); self.assertFalse(b.tripped)
        b.fail("c"); self.assertTrue(b.tripped)

    def test_a_success_resets_the_count(self):
        b = F.Breaker(3)
        b.fail("a"); b.fail("b"); b.ok(); b.fail("c"); b.fail("d")
        self.assertFalse(b.tripped)

    def test_failed_and_skipped_backfill_bills_go_back_on_the_queue(self):
        b = F.Breaker(3)
        b.fail("119-hr2"); b.skipped.add("119-hr9"); b.skipped.add("119-s1")  # 119-s1 isn't in this batch
        self.assertEqual(F.requeue(["119-hr1", "119-hr2", "119-hr9"], b), ["119-hr2", "119-hr9"])


class TimeBudget(unittest.TestCase):
    """A half-working Congress.gov: successes reset the failure count, so time has to stop it."""

    def clock(self):
        t = [0.0]
        return t, (lambda: t[0])

    def test_stops_when_the_budget_is_used_up(self):
        t, clk = self.clock()
        b = F.Breaker(3, 420, clk)
        self.assertFalse(b.stop())
        for _ in range(4):  # fail, ok, fail, ok: never 3 in a row
            b.fail("x"); t[0] += 100; b.ok(); t[0] += 10
        self.assertFalse(b.tripped)
        self.assertTrue(b.stop())
        self.assertTrue(b.out_of_time)

    def test_slow_with_failures_counts_as_down_for_the_note(self):
        t, clk = self.clock()
        b = F.Breaker(3, 420, clk)
        b.fail("119-hr1"); b.ok(); t[0] = 500
        b.stop()
        self.assertTrue(b.struggling)

    def test_slow_but_every_bill_worked_is_not_an_outage(self):
        t, clk = self.clock()
        b = F.Breaker(3, 420, clk)
        b.ok(); t[0] = 500
        self.assertTrue(b.stop())
        self.assertFalse(b.struggling)

    def test_bills_skipped_for_time_go_back_on_the_queue(self):
        t, clk = self.clock()
        b = F.Breaker(3, 420, clk)
        t[0] = 500
        for bid in ("119-hr1", "119-hr2"):
            if b.stop():
                b.skipped.add(bid)
        self.assertEqual(F.requeue(["119-hr1", "119-hr2", "119-hr3"], b), ["119-hr1", "119-hr2"])

    def test_no_budget_never_runs_out(self):
        t, clk = self.clock()
        b = F.Breaker(3, None, clk)
        t[0] = 1e9
        self.assertFalse(b.stop())

class OutageNote(unittest.TestCase):
    """The visitor note only for a sustained Congress.gov outage, never for a one-run blip."""
    import datetime as _dt
    T0 = _dt.datetime(2026, 11, 7, 18, 17, tzinfo=_dt.timezone.utc)

    def at(self, minutes):
        return self.T0 + self._dt.timedelta(minutes=minutes)

    def test_first_failed_run_starts_the_clock_but_shows_nothing(self):
        since, note = F.outage_state(None, True, self.T0, None)
        self.assertEqual(since, "2026-11-07T18:17:00+00:00")
        self.assertIsNone(note)

    def test_next_failed_run_shows_the_note_with_the_first_failure_time(self):
        since, note = F.outage_state("2026-11-07T18:17:00+00:00", True, self.at(30), None)
        self.assertEqual(note, {"since": "2026-11-07T18:17:00+00:00"})
        self.assertEqual(since, "2026-11-07T18:17:00+00:00")

    def test_note_stays_identical_while_down_so_nothing_new_commits(self):
        a = F.outage_state("2026-11-07T18:17:00+00:00", True, self.at(60), None)
        b = F.outage_state("2026-11-07T18:17:00+00:00", True, self.at(600), a[1])
        self.assertEqual(a, b)

    def test_a_quick_chained_rerun_does_not_count_as_a_second_failure(self):
        self.assertIsNone(F.outage_state("2026-11-07T18:17:00+00:00", True, self.at(5), None)[1])

    def test_recovery_clears_everything(self):
        self.assertEqual(F.outage_state("2026-11-07T18:17:00+00:00", False, self.at(90), {"since": "x"}), (None, None))

    def test_a_blip_never_reaches_the_site(self):
        since, note = F.outage_state(None, True, self.T0, None)
        self.assertIsNone(note)
        self.assertEqual(F.outage_state(since, False, self.at(30), note), (None, None))

    def test_a_run_that_did_not_check_keeps_the_state(self):
        self.assertEqual(F.outage_state("2026-11-07T18:17:00+00:00", None, self.at(30), {"since": "2026-11-07T18:17:00+00:00"}),
                         ("2026-11-07T18:17:00+00:00", {"since": "2026-11-07T18:17:00+00:00"}))
        self.assertEqual(F.outage_state(None, None, self.at(30), None), (None, None))

    def test_unreadable_start_time_restarts_the_clock(self):
        since, note = F.outage_state("garbage", True, self.T0, None)
        self.assertEqual((since, note), ("2026-11-07T18:17:00+00:00", None))

    def test_the_note_is_data_so_its_start_and_end_commit(self):
        base = {"bills": [], "generatedAt": "a"}
        self.assertTrue(F.data_changed(json.dumps({**base, "outage": {"since": "x"}}), json.dumps(base)))
        self.assertFalse(F.data_changed(json.dumps({**base, "outage": {"since": "x"}, "generatedAt": "b"}),
                                        json.dumps({**base, "outage": {"since": "x"}})))


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
