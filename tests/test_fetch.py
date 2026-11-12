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


class PresidentByDate(unittest.TestCase):
    """Biden through Jan 20, 2025, Trump after. Inauguration days count for the outgoing president."""

    def test_the_2025_cutoff(self):
        self.assertEqual(F.president_on("2025-01-19"), ("Joe Biden", "D"))
        self.assertEqual(F.president_on("2025-01-20"), ("Joe Biden", "D"))
        self.assertEqual(F.president_on("2025-01-21"), ("Donald Trump", "R"))
        self.assertEqual(F.president_on("2026-07-04"), ("Donald Trump", "R"))

    def test_earlier_terms_follow_the_same_rule(self):
        self.assertEqual(F.president_on("2021-01-20"), ("Donald Trump", "R"))
        self.assertEqual(F.president_on("2021-01-21"), ("Joe Biden", "D"))
        self.assertEqual(F.president_on("2017-01-21"), ("Donald Trump", "R"))
        self.assertEqual(F.president_on("2009-06-01"), ("Barack Obama", "D"))

    def test_unknown_dates(self):
        self.assertIsNone(F.president_on(None))
        self.assertIsNone(F.president_on(""))
        self.assertIsNone(F.president_on("1990-05-01"))

    def test_timestamps_use_the_day(self):
        self.assertEqual(F.president_on("2025-01-20T23:59:00Z"), ("Joe Biden", "D"))


def act(d, t):
    return {"actionDate": d, "text": t}


class Outcomes(unittest.TestCase):
    URL = "https://www.congress.gov/bill/119th-congress/house-bill/1"

    def test_signed_law_names_the_president_and_the_signing_date(self):
        actions = [act("2025-07-04", "Became Public Law No: 119-21."), act("2025-07-04", "Signed by President."),
                   act("2025-07-03", "Presented to President."), act("2025-07-03", "Resolving differences -- House actions: On motion that the House agree to the Senate amendment Agreed to by the Yeas and Nays: 218 - 214 (Roll no. 190).")]
        o, fns = F.outcome_from(actions, [{"number": "119-21"}], "law", self.URL)
        self.assertEqual((o["where"], o["d"], o["pres"], o["pp"], o["by"], o["fn"]), ("Signed into law", "2025-07-04", "Donald Trump", "R", "Donald Trump", "sig"))
        self.assertIn("Signed by President", fns["sig"]["t"])
        self.assertEqual(fns["sig"]["u"], self.URL + "/all-actions")

    def test_signing_date_not_latest_action(self):
        actions = [act("2025-09-02", "Some later housekeeping."), act("2025-08-01", "Became Public Law No: 119-40."), act("2025-08-01", "Signed by President.")]
        o, _ = F.outcome_from(actions, [{"number": "119-40"}], "law", self.URL)
        self.assertEqual(o["d"], "2025-08-01")

    def test_law_without_signature(self):
        o, _ = F.outcome_from([act("2025-05-01", "Became Public Law No: 119-9 without the President's signature.")], [{"number": "119-9"}], "law", self.URL)
        self.assertEqual((o["where"], o["how"], o["pres"]), ("Became law without signature", "unsigned", "Donald Trump"))

    def test_veto_with_message_and_failed_override(self):
        actions = [act("2026-01-08", "On passage, the objections of the President to the contrary notwithstanding Failed by the Yeas and Nays: (2/3 required): 248 - 177 (Roll no. 9)."),
                   act("2026-01-02", "Veto message received in House and ordered printed as a House Document (H. Doc. 119-119)."),
                   act("2025-12-29", "Vetoed by President."), act("2025-12-17", "Presented to President.")]
        o, fns = F.outcome_from(actions, [], "vetoed", self.URL)
        self.assertEqual((o["where"], o["d"], o["pres"], o["by"]), ("Vetoed", "2025-12-29", "Donald Trump", "Donald Trump"))
        self.assertEqual(o["msg"], "https://www.govinfo.gov/app/details/CDOC-119hdoc119")
        self.assertEqual(o["v"], "Override failed 248–177")
        self.assertIn("veto", fns)

    def test_veto_in_congress_gov_s_real_wording(self):
        # H.R. 131 as Congress.gov lists it: "House Document (119-119)" and the override recorded twice
        actions = [act("2025-12-29", "Vetoed by President."),
                   act("2026-01-02", "The Chair announced that the objections of the President to H.R. 131 would be spread at large upon the Journal, and the veto message would be printed as a House Document (119-119)."),
                   act("2026-01-08", "On passage, the objections of the President to the contrary notwithstanding Failed by the Yeas and Nays: (2/3 required): 248 - 177, 1 Present (Roll no. 9)."),
                   act("2026-01-08", "Failed of passage in House over veto")]
        o, _ = F.outcome_from(actions, [], "vetoed", self.URL)
        self.assertEqual((o["msg"], o["msgLabel"]), ("https://www.govinfo.gov/app/details/CDOC-119hdoc119", "H. Doc. 119-119"))
        self.assertEqual(o["v"], "Override failed 248–177")

    def test_veto_without_an_override_vote_has_no_tally(self):
        o, _ = F.outcome_from([act("2025-12-29", "Vetoed by President.")], [], "vetoed", self.URL)
        self.assertEqual((o["v"], o.get("msg")), ("", None))

    def test_veto_overridden_into_law(self):
        actions = [act("2026-03-01", "Became Public Law No: 119-80."), act("2026-02-20", "Passed Senate over veto by Yea-Nay Vote. 70 - 30."),
                   act("2026-02-01", "Vetoed by President.")]
        o, _ = F.outcome_from(actions, [{"number": "119-80"}], "law", self.URL)
        self.assertEqual((o["where"], o["how"], o["pres"]), ("Became law over a veto", "override", "Donald Trump"))

    def test_nothing_for_other_bills(self):
        self.assertEqual(F.outcome_from([act("2025-03-01", "Passed Senate by Unanimous Consent.")], [], "passed1", self.URL), (None, {}))

    def test_same_actions_same_result(self):
        actions = [act("2025-07-04", "Became Public Law No: 119-21."), act("2025-07-04", "Signed by President.")]
        self.assertEqual(F.outcome_from(actions, [{"number": "119-21"}], "law", self.URL), F.outcome_from(list(reversed(actions)), [{"number": "119-21"}], "law", self.URL))


class Passages(unittest.TestCase):
    def test_roll_call_voice_and_consent(self):
        p = F.passages([act("2026-04-30", "Passed/agreed to in House: On passage Passed by the Yeas and Nays: 224 - 200 (Roll no. 154)."),
                        act("2026-06-10", "Passed/agreed to in Senate: Passed Senate without amendment by Unanimous Consent.")])
        self.assertEqual(p, {"H": {"d": "2026-04-30", "how": "roll", "v": "224–200", "roll": 154}, "S": {"d": "2026-06-10", "how": "uc"}})
        self.assertEqual(F.passages([act("2025-03-03", "Passed/agreed to in House: On motion to suspend the rules and pass the bill Agreed to by voice vote.")])["H"]["how"], "voice")

    def test_senate_record_vote(self):
        p = F.passages([act("2025-07-01", "Passed/agreed to in Senate: Passed Senate with an amendment by Yea-Nay Vote. 51 - 50. Record Vote Number: 372.")])
        self.assertEqual(p["S"], {"d": "2025-07-01", "how": "roll", "v": "51–50", "roll": 372})

    def test_final_vote_wins_and_failures_are_ignored(self):
        p = F.passages([act("2025-05-22", "Passed/agreed to in House: On passage Passed by the Yeas and Nays: 215 - 214 (Roll no. 145)."),
                        act("2025-07-03", "Resolving differences -- House actions: On motion that the House agree to the Senate amendment Agreed to by the Yeas and Nays: 218 - 214 (Roll no. 190)."),
                        act("2025-07-03", "On motion to recommit Failed by the Yeas and Nays: 207 - 216 (Roll no. 189).")])
        self.assertEqual((p["H"]["d"], p["H"]["roll"]), ("2025-07-03", 190))

    def test_same_day_duplicate_keeps_the_roll_number(self):
        p = F.passages([act("2026-04-30", "Passed/agreed to in House: On passage Passed by the Yeas and Nays: 224 - 200 (Roll no. 154)."),
                        act("2026-04-30", "Passed/agreed to in House: On passage Passed.")])
        self.assertEqual(p["H"]["roll"], 154)


class MergeAndCommits(unittest.TestCase):
    def test_curated_note_stays_and_the_president_comes_through(self):
        auto = {"outcome": {"where": "Signed into law", "by": "Donald Trump", "pres": "Donald Trump", "pp": "R", "d": "2025-07-04", "fn": "sig"},
                "fns": {"sig": {"t": "signed"}}, "url": "u"}
        cur = {"outcome": {"by": "Party-line reconciliation; VP tiebreak", "d": "2025-07-04", "fn": "d", "v": "218–214"}, "fns": {"d": {"t": "curated"}}}
        b = F.merge(auto, cur)
        self.assertEqual(b["outcome"]["by"], "Party-line reconciliation; VP tiebreak")
        self.assertEqual((b["outcome"]["pres"], b["outcome"]["fn"], b["outcome"]["fn2"]), ("Donald Trump", "d", "sig"))
        self.assertEqual(set(b["fns"]), {"sig", "d", "cg"})

    def test_blank_curated_by_gets_the_president(self):
        b = F.merge({"outcome": {"by": "Donald Trump", "pres": "Donald Trump", "fn": "sig"}}, {"outcome": {"by": "", "v": "x"}})
        self.assertEqual(b["outcome"]["by"], "Donald Trump")

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


class Schedule(unittest.TestCase):
    """Bill checks are due by time since the last good one, so dropped GitHub runs only delay them."""
    import datetime as _dt
    CAL = {"house": [{"f": "2026-11-09", "t": "2026-11-13"}]}

    def at(self, day, hour_ct, minute=17):
        return self._dt.datetime(2026, 11, day, hour_ct + 6, minute, tzinfo=self._dt.timezone.utc) if hour_ct + 6 < 24 else \
            self._dt.datetime(2026, 11, day + 1, hour_ct - 18, minute, tzinfo=self._dt.timezone.utc)

    def iso(self, d):
        return d.isoformat(timespec="seconds")

    def test_a_run_outside_the_old_check_hours_still_checks_bills(self):
        # yesterday's runs came at 9:41, 2:15, 5:41 and 12:07; none was in the old 6/12/18/23 hours
        last = self.iso(self.at(9, 6))
        self.assertEqual(F.plan("auto", self.at(9, 14, 15), self.CAL, last), (True, True))

    def test_in_session_not_again_until_five_hours_pass(self):
        last = self.iso(self.at(9, 9))
        self.assertFalse(F.plan("auto", self.at(9, 13, 47), self.CAL, last)[0])
        self.assertTrue(F.plan("auto", self.at(9, 14, 17), self.CAL, last)[0])

    def test_recess_about_once_a_day(self):
        last = self.iso(self.at(8, 9))
        self.assertFalse(F.plan("auto", self.at(8, 20), {}, last)[0])
        self.assertTrue(F.plan("auto", self.at(9, 6), {}, last)[0])  # 21 hours later

    def test_quiet_overnight(self):
        self.assertEqual(F.plan("auto", self.at(9, 3), self.CAL, None), (False, False))

    def test_never_checked_is_due(self):
        self.assertTrue(F.plan("auto", self.at(8, 7), {}, None)[0])
        self.assertTrue(F.plan("auto", self.at(8, 7), {}, "garbage")[0])

    def test_votes_only_on_session_days_from_8_am(self):
        self.assertFalse(F.plan("auto", self.at(9, 7), self.CAL, None)[1])
        self.assertTrue(F.plan("auto", self.at(9, 8), self.CAL, None)[1])
        self.assertFalse(F.plan("auto", self.at(8, 12), self.CAL, None)[1])

    def test_modes_still_override(self):
        self.assertEqual(F.plan("full", self.at(9, 3), {}, None), (True, True))
        self.assertEqual(F.plan("votes", self.at(9, 3), {}, None), (False, True))
        self.assertEqual(F.plan("offline", self.at(9, 12), self.CAL, None), (False, False))


class Vehicles(unittest.TestCase):
    """data/vehicles.json: a bill's number carrying a different bill's text."""
    ENTRY = {"bill": "119-hr2347", "carries": "119-s5653", "label": "Bipartisan American Affordability and Jobs Act",
             "since": "2026-11-09", "source": "https://www.dailypress.senate.gov/monday-november-9-2026/"}

    def test_the_repo_file_reads_and_lists_hr2347(self):
        raw = json.loads((Path(__file__).resolve().parent.parent / "data" / "vehicles.json").read_text())
        self.assertIn("119-hr2347", F.load_vehicles(raw))

    def test_note_and_footnote(self):
        v, fn = F.vehicle_note(self.ENTRY)
        self.assertEqual(v, {"carries": "119-s5653", "num": "S. 5653", "label": "Bipartisan American Affordability and Jobs Act",
                             "since": "2026-11-09", "fn": "veh"})
        self.assertEqual(fn, {"src": "Senate Daily Press", "t": "vehicle for S. 5653 since Nov 9, 2026",
                              "u": "https://www.dailypress.senate.gov/monday-november-9-2026/"})

    def test_bill_numbers_read_naturally(self):
        self.assertEqual([F.bill_num(x) for x in ("119-s5653", "119-hr2347", "119-hjres104", "bad")],
                         ["S. 5653", "H.R. 2347", "H.J.Res. 104", "bad"])

    def test_unknown_source_falls_back_to_its_host(self):
        self.assertEqual(F.source_name("https://www.example.org/x"), "example.org")

    def test_bad_entries_are_skipped_not_fatal(self):
        bad = [{**self.ENTRY, "bill": "hr2347-119"}, {**self.ENTRY, "since": "11/9/2026"},
               {**self.ENTRY, "source": "http://insecure.example"}, None, {}]
        F.WARN.clear()
        self.assertEqual(F.load_vehicles({"vehicles": bad + [self.ENTRY]}), {"119-hr2347": self.ENTRY})
        self.assertEqual(len(F.WARN), 5)  # one per bad entry

    def test_missing_or_empty_file_means_no_vehicles(self):
        self.assertEqual(F.load_vehicles({}), {})
        self.assertEqual(F.load_vehicles(None), {})


def clerk_xml(n, day="10-Nov-2026", legis="H RES 1601", q="On Motion to Table", desc="Impeaching Peter B. Hegseth, Secretary of Defense", y=220, no=205):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rollcall-vote><vote-metadata><majority>R</majority><congress>119</congress><session>2nd</session>
<chamber>U.S. House of Representatives</chamber><rollcall-num>{n}</rollcall-num><legis-num>{legis}</legis-num>
<vote-question>{q}</vote-question><vote-type>YEA-AND-NAY</vote-type><vote-result>Passed</vote-result>
<action-date>{day}</action-date><action-time time-etz="15:02">3:02 PM</action-time><vote-desc>{desc}</vote-desc>
<vote-totals><totals-by-party><party>Republican</party><yea-total>200</yea-total><nay-total>10</nay-total><present-total>1</present-total><not-voting-total>7</not-voting-total></totals-by-party>
<totals-by-vote><total-stub>Totals</total-stub><yea-total>{y}</yea-total><nay-total>{no}</nay-total><present-total>0</present-total><not-voting-total>8</not-voting-total></totals-by-vote>
</vote-totals></vote-metadata><vote-data></vote-data></rollcall-vote>""".encode()


class ClerkHouseVotes(unittest.TestCase):
    """House roll calls from the Clerk's XML, since Congress.gov's feed stopped at roll 306."""
    import datetime as _dt
    NOW = _dt.datetime(2026, 11, 11, 3, 0, tzinfo=_dt.timezone.utc)  # Nov 10 evening, Central

    def fetcher(self, posted):
        calls = []
        def fetch(url):
            calls.append(url)
            n = int(url.rsplit("roll", 1)[1].split(".")[0])
            if n in posted:
                return posted[n]
            raise F.urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return fetch, calls

    def test_reads_a_clerk_roll_call(self):
        v = F.parse_clerk_vote(clerk_xml(318))
        self.assertEqual(v, {"ch": "H", "n": 318, "p": {"R": [200, 10, 1, 7]}, "d": "2026-11-10", "type": "Yea-And-Nay", "q": "On Motion to Table",
                             "measure": "HRES 1601", "title": "Impeaching Peter B. Hegseth, Secretary of Defense",
                             "result": "Passed", "y": "220", "n_": "205", "u": "https://clerk.house.gov/Votes/2026318"})

    def test_measure_numbers(self):
        self.assertEqual([F.clerk_measure(x) for x in ("H R 9612", "H RES 1601", "H J RES 210", "S 5653", "QUORUM", "")],
                         ["HR 9612", "HRES 1601", "HJRES 210", "S 5653", "", ""])

    def test_bad_xml_is_skipped(self):
        self.assertIsNone(F.parse_clerk_vote(b"<html>error</html>"))
        self.assertIsNone(F.parse_clerk_vote(b"not xml"))

    def test_picks_up_new_roll_calls_after_what_the_site_has(self):
        prev = [{"ch": "H", "n": 306, "d": "2026-09-15", "q": "On Passage", "y": "216", "n_": "211"}]
        fetch, calls = self.fetcher({307: clerk_xml(307, "16-Sep-2026"), 308: clerk_xml(308)})
        state = {}
        out = F.clerk_house_votes(self.NOW, state, prev, fetch)
        self.assertEqual([v["n"] for v in out], [308, 307, 306])
        self.assertEqual(calls[-1].endswith("roll309.xml"), True)  # one miss, then stop
        self.assertEqual(len(calls), 3)

    def test_nothing_new_costs_one_request(self):
        state = {}
        fetch, calls = self.fetcher({})
        F.clerk_house_votes(self.NOW, state, [{"ch": "H", "n": 318, "d": "2026-11-10"}], fetch)
        self.assertEqual(len(calls), 1)

    def test_keeps_the_60_newest(self):
        posted = {n: clerk_xml(n) for n in range(1, 71)}
        fetch, _ = self.fetcher(posted)
        F.CLERK_NEW_PER_RUN, old = 100, F.CLERK_NEW_PER_RUN
        try:
            state = {}
            out = F.clerk_house_votes(self.NOW, state, [], fetch)
        finally:
            F.CLERK_NEW_PER_RUN = old
        self.assertEqual((len(out), out[0]["n"], out[-1]["n"], len(state["clerkVotes"])), (60, 70, 11, 60))

    def test_new_year_starts_over(self):
        state = {"clerkVotes": {"2025-400": {"n": 400, "d": "2025-12-18"}}}
        fetch, calls = self.fetcher({1: clerk_xml(1, "6-Jan-2026")})
        out = F.clerk_house_votes(self.NOW, state, [{"n": 400, "d": "2025-12-18"}], fetch)
        self.assertEqual([v["n"] for v in out], [1])
        self.assertTrue(calls[0].endswith("/2026/roll001.xml"))

    def test_clerk_down_falls_back_to_congress_gov_then_keeps_what_we_had(self):
        old = (F.clerk_house_votes, F.house_votes)
        def down(*a, **k):
            raise TimeoutError("no route")
        F.clerk_house_votes = down
        try:
            F.house_votes = lambda *a, **k: [{"n": 1}]
            self.assertEqual(F.house_with_fallback(119, 2, self.NOW, {}, [{"n": 0}]), [{"n": 1}])
            F.house_votes = lambda *a, **k: []
            self.assertEqual(F.house_with_fallback(119, 2, self.NOW, {}, [{"n": 0}]), [{"n": 0}])
        finally:
            F.clerk_house_votes, F.house_votes = old


FLOOR_XML = """<floorschedule congress-num="119" week-date="2026-11-09" update-date="2026-11-10T09:25:12.060">
  <current-status>R</current-status><language>en-us</language>
  <category type="Items that may be considered under suspension of the rules" sort-order="1"><floor-items>
    <floor-item id="1" add-date="2026-11-02" remove-date="" sort-order="1"><legis-num>H.R. 3978</legis-num><floor-text>Nuclear REFUEL Act, as amended</floor-text></floor-item>
  </floor-items></category>
  <category type="Items that may be considered pursuant to a rule" sort-order="4"><floor-items>
    <floor-item id="2" add-date="2026-11-05" remove-date="" sort-order="1"><legis-num>H.R. 1013</legis-num><floor-text>Retirement Fairness for Charities and Educational Institutions Act of 2025</floor-text></floor-item>
    <floor-item id="3" add-date="2026-11-05" remove-date="2026-11-06" sort-order="2"><legis-num>H.R. 77</legis-num><floor-text>Pulled Act</floor-text></floor-item>
  </floor-items></category>
  <category type="Items that may be considered" sort-order="5"><floor-items>
    <floor-item id="4" add-date="2026-11-09" remove-date="" sort-order="1"><legis-num>H. Res. 1650</legis-num><floor-text>Providing for consideration of the bill (H.R. 1013)</floor-text></floor-item>
    <floor-item id="5" add-date="2026-11-09" remove-date="" sort-order="2"><legis-num>H. Res. ___</legis-num><floor-text>Impeaching Peter Brian Hegseth, Secretary of Defense, for high crimes and misdemeanors.</floor-text></floor-item>
  </floor-items></category>
</floorschedule>""".encode()


class HouseFloor(unittest.TestCase):
    import datetime as _dt
    TUE = _dt.datetime(2026, 11, 10, 20, 0, tzinfo=_dt.timezone.utc)

    def test_keeps_rule_bills_and_privileged_items_only(self):
        f = F.parse_house_floor(FLOOR_XML, 119)
        self.assertEqual(f["week"], "2026-11-09")
        self.assertEqual(f["items"], [
            {"num": "H.R. 1013", "id": "119-hr1013", "t": "Retirement Fairness for Charities and Educational Institutions Act of 2025", "how": "rule"},
            {"num": "", "id": "", "t": "Impeaching Peter Brian Hegseth, Secretary of Defense, for high crimes and misdemeanors.", "how": "other"}])
        self.assertEqual(f["u"], "https://docs.house.gov/floor/Default.aspx?date=2026-11-09")

    def test_week_shown(self):
        self.assertEqual(F.floor_week(self.TUE).isoformat(), "2026-11-09")
        sat = self._dt.datetime(2026, 11, 14, 18, 0, tzinfo=self._dt.timezone.utc)
        self.assertEqual(F.floor_week(sat).isoformat(), "2026-11-16")  # from Saturday, next week

    def test_down_keeps_this_weeks_copy_but_never_last_weeks(self):
        def down(u):
            raise TimeoutError("no route")
        F.DOWN.clear()
        this = {"week": "2026-11-09", "items": [{"t": "x"}]}
        self.assertEqual(F.house_floor(self.TUE, 119, this, down), this)
        self.assertTrue(F.DOWN["hfloor"])
        self.assertIsNone(F.house_floor(self.TUE, 119, {"week": "2026-11-02", "items": []}, down))

    def test_nothing_posted_is_not_an_outage(self):
        def missing(u):
            raise F.urllib.error.HTTPError(u, 404, "Not Found", {}, None)
        F.DOWN.clear()
        self.assertIsNone(F.house_floor(self.TUE, 119, None, missing))
        self.assertFalse(F.DOWN["hfloor"])

    def test_unreadable_file_keeps_the_last_copy(self):
        F.DOWN.clear()
        this = {"week": "2026-11-09", "items": []}
        self.assertEqual(F.house_floor(self.TUE, 119, this, lambda u: b"<html>oops</html>"), this)
        self.assertTrue(F.DOWN["hfloor"])

    def test_asks_for_the_right_file(self):
        seen = []
        F.house_floor(self.TUE, 119, None, lambda u: seen.append(u) or FLOOR_XML)
        self.assertEqual(seen, ["https://docs.house.gov/floor/Download.aspx?file=/billsthisweek/20261109/20261109.xml"])


class SenateClotureAhead(unittest.TestCase):
    import datetime as _dt
    DAYS = {"2026-11-09", "2026-11-10", "2026-11-16", "2026-11-17", "2026-11-18"}

    def bill(self, *tl):
        return {"id": "119-hr1", "num": "H.R. 1", "timeline": [{"d": d, "e": e} for d, e in tl]}

    def test_filing_waits_for_the_second_day_or_next_session_day(self):
        b = self.bill(("2026-11-10", "Cloture motion on the motion to proceed to the measure presented in Senate. (CR S5241)"))
        out = F.senate_cloture_ahead([b], self.DAYS, self._dt.date(2026, 11, 10))
        self.assertEqual(out, [{"id": "119-hr1", "num": "H.R. 1", "filed": "2026-11-10", "expected": "2026-11-16", "on": "motion to proceed"}])

    def test_gone_once_the_vote_happens(self):
        b = self.bill(("2026-09-30", "Cloture motion on the motion to proceed to the measure presented in Senate. (CR S5241)"),
                      ("2026-11-09", "Cloture on the motion to proceed to the measure invoked in Senate by Yea-Nay Vote. 73 - 25. Record Vote Number: 257."))
        self.assertEqual(F.senate_cloture_ahead([b], self.DAYS, self._dt.date(2026, 11, 10)), [])

    def test_not_invoked_and_withdrawn_also_end_it(self):
        for done in ("Cloture on the motion to proceed to the measure not invoked in Senate by Yea-Nay Vote. 53 - 47.",
                     "Cloture motion on the motion to proceed to the measure withdrawn by unanimous consent in Senate."):
            b = self.bill(("2026-11-09", "Cloture motion on the measure presented in Senate."), ("2026-11-10", done))
            self.assertEqual(F.senate_cloture_ahead([b], self.DAYS, self._dt.date(2026, 11, 10)), [])

    def test_a_vote_that_didnt_happen_when_expected_is_dropped(self):
        b = self.bill(("2026-09-30", "Cloture motion on the measure presented in Senate."))
        self.assertEqual(F.senate_cloture_ahead([b], set(), self._dt.date(2026, 11, 10)), [])

    def test_no_timeline_no_problem(self):
        self.assertEqual(F.senate_cloture_ahead([{"id": "x"}, {"id": "y", "timeline": [{"e": "no date"}]}], self.DAYS, self._dt.date(2026, 11, 10)), [])


class AllSourcesOutage(unittest.TestCase):
    import datetime as _dt
    T0 = _dt.datetime(2026, 11, 10, 18, 0, tzinfo=_dt.timezone.utc)

    def test_each_source_on_its_own_clock(self):
        t1 = self.T0 + self._dt.timedelta(minutes=30)
        since, note = F.outages({}, {}, {"clerk": True, "congress": False}, self.T0)
        self.assertEqual((since, note), ({"clerk": "2026-11-10T18:00:00+00:00"}, {}))
        since, note = F.outages(since, note, {"clerk": True, "voteview": True}, t1)
        self.assertEqual(note, {"clerk": "2026-11-10T18:00:00+00:00"})  # voteview only just started
        self.assertIn("voteview", since)
        since, note = F.outages(since, note, {"clerk": False}, t1 + self._dt.timedelta(minutes=30))
        self.assertEqual(note, {})  # clerk cleared; voteview has failed only once, and wasn't asked again
        self.assertEqual(set(since), {"voteview"})  # so its clock keeps running
        since, note = F.outages(since, note, {"voteview": True}, t1 + self._dt.timedelta(minutes=60))
        self.assertEqual(set(note), {"voteview"})  # a later failed check: now it shows

    def test_older_site_data_reads_as_congress_gov(self):
        self.assertEqual(F.shown_outages({"since": "x"}), {"congress": "x"})
        self.assertEqual(F.shown_outages({"since": "x", "sources": {"clerk": "y"}}), {"clerk": "y"})
        self.assertEqual(F.shown_outages(None), {})


class FreshRollCalls(unittest.TestCase):
    """A bill dropped for no floor action comes back when it gets a roll call (H.R. 1013, Nov 11)."""
    VOTES = {"house": [{"n": 321, "d": "2026-11-11", "measure": "HR 1013", "q": "On Passage"},
                       {"n": 320, "d": "2026-11-11", "measure": "HRES 1247", "q": "On Motion to Discharge"}],
             "senate": [{"n": 257, "d": "2026-11-09", "measure": "HR2347"}, {"n": 256, "d": "2026-09-30", "measure": "PN1129"}]}

    def test_dropped_bill_with_a_new_roll_call_is_rechecked(self):
        t = {"bills": ["119-hr2347"], "dropped": ["119-hr1013"]}
        self.assertEqual(F.fresh_rollcall_bills(self.VOTES, 119, t, []), ["119-hr1013"])

    def test_each_roll_call_date_is_looked_at_once(self):
        t = {"bills": [], "dropped": []}
        self.assertEqual(F.fresh_rollcall_bills(self.VOTES, 119, t, []), ["119-hr1013", "119-hr2347"])
        self.assertEqual(F.fresh_rollcall_bills(self.VOTES, 119, t, []), [])  # still not tracked, same votes: no loop
        later = {"house": [{"n": 330, "d": "2026-11-13", "measure": "HR 1013"}]}
        self.assertEqual(F.fresh_rollcall_bills(later, 119, t, []), ["119-hr1013"])  # a newer roll call: look again

    def test_resolutions_nominations_tracked_and_queued_are_skipped(self):
        t = {"bills": ["119-hr2347"], "dropped": []}
        self.assertEqual(F.fresh_rollcall_bills(self.VOTES, 119, t, ["119-hr1013"]), [])

    def test_bad_records_are_ignored(self):
        self.assertEqual(F.fresh_rollcall_bills({"house": [None, {}, {"measure": "HR 5"}, {"measure": "QUORUM", "d": "2026-11-11"}]}, 119, {"bills": []}, []), [])

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
