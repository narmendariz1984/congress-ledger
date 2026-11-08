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
