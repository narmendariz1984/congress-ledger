"""Checks for scripts/rollcalls.py (Voteview roll calls and member votes). No network."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import rollcalls as R  # noqa: E402


def csv_rows(text):
    return R.rows(text.encode())


MEMBERS = csv_rows(
    "congress,chamber,icpsr,state_icpsr,district_code,state_abbrev,party_code,bioname\n"
    "119,House,1,0,5,MN,100,\"OMAR, Ilhan\"\n"
    "119,House,2,0,15,PA,200,\"THOMPSON, Glenn (G.T.)\"\n"
    "119,House,3,0,4,KY,200,\"MASSIE, Thomas Harold\"\n"
    "119,President,9,0,0,USA,200,\"TRUMP, Donald John\"\n")
ROLLS = csv_rows(
    "congress,chamber,rollnumber,date,session,clerk_rollnumber,yea_count,nay_count,bill_number,vote_result,vote_desc,vote_question\n"
    "119,House,10,2026-04-30,2,154,2,1,HR7567,Passed,\"Farm, Food &amp; National Security Act\",On Passage\n"
    "119,House,11,2026-05-01,2,155,0,0,,Passed,,Call of the House\n")
VOTES = csv_rows(
    "congress,chamber,rollnumber,icpsr,cast_code,prob\n"
    "119,House,10,1,6,99\n119,House,10,2,1,99\n119,House,10,3,9,50\n119,President,10,9,1,99\n")


class Names(unittest.TestCase):
    def test_voteview_names_read_naturally(self):
        self.assertEqual(R.person_name("OMAR, Ilhan"), "Ilhan Omar")
        self.assertEqual(R.person_name("THOMPSON, Glenn (G.T.)"), "G.T. Thompson")
        self.assertEqual(R.person_name("McCARTHY, Kevin"), "Kevin McCarthy")
        self.assertEqual(R.person_name("MCCOLLUM, Betty"), "Betty McCollum")
        self.assertEqual(R.person_name("MACE, Nancy"), "Nancy Mace")
        self.assertEqual(R.person_name("DeLAURO, Rosa L."), "Rosa DeLauro")
        self.assertEqual(R.person_name("O'ROURKE, Robert"), "Robert O'Rourke")
        self.assertEqual(R.person_name("CRUZ, Rafael Edward (Ted)"), "Ted Cruz")
        self.assertEqual(R.person_name("VAN HOLLEN, Christopher, Jr."), "Christopher Van Hollen")
        self.assertEqual(R.person_name("OCASIO-CORTEZ, Alexandria"), "Alexandria Ocasio-Cortez")


class Build(unittest.TestCase):
    def setUp(self):
        self.members, self.votes = R.build("H", ROLLS, MEMBERS, VOTES)

    def test_members_in_fixed_order_without_the_president(self):
        self.assertEqual([m["n"] for m in self.members], ["Ilhan Omar", "G.T. Thompson", "Thomas Massie"])
        self.assertEqual(self.members[0], {"id": 1, "n": "Ilhan Omar", "p": "D", "s": "MN", "d": 5})

    def test_vote_string_follows_member_order(self):
        v = next(x for x in self.votes if x["r"] == 10)
        self.assertEqual(v["v"], "NY.")
        self.assertEqual((v["n"], v["y"], v["no"], v["m"], v["q"]), (154, 2, 1, "HR7567", "On Passage"))
        self.assertEqual(v["t"], "Farm, Food & National Security Act")

    def test_roll_call_without_member_votes_gets_an_empty_string(self):
        self.assertEqual(next(x for x in self.votes if x["r"] == 11)["v"], "")

    def test_newest_first(self):
        self.assertEqual([x["r"] for x in self.votes], [11, 10])


class Interval(unittest.TestCase):
    def test_recent_check_skips_without_network(self):
        with tempfile.TemporaryDirectory() as d:
            old = (R.OUT, R.STATE, R.get)
            R.OUT, R.STATE = Path(d) / "rollcalls.json", Path(d) / "state.json"
            R.OUT.write_text("{}")
            import datetime as dt
            R.STATE.write_text(json.dumps({"lastCheck": dt.datetime.now(dt.timezone.utc).isoformat()}))

            def boom(*a, **k):
                raise AssertionError("should not download")
            R.get = boom
            os.environ.pop("FORCE", None)
            try:
                self.assertEqual(R.main(), 0)
            finally:
                R.OUT, R.STATE, R.get = old

    def test_unreachable_voteview_keeps_the_last_file(self):
        with tempfile.TemporaryDirectory() as d:
            old = (R.OUT, R.STATE, R.get)
            R.OUT, R.STATE = Path(d) / "rollcalls.json", Path(d) / "state.json"
            R.OUT.write_text('{"keep": true}')

            def down(*a, **k):
                raise TimeoutError("no route")
            R.get = down
            os.environ["FORCE"] = "1"
            try:
                self.assertEqual(R.main(), 0)
                self.assertEqual(R.OUT.read_text(), '{"keep": true}')
            finally:
                os.environ.pop("FORCE", None)
                R.OUT, R.STATE, R.get = old


if __name__ == "__main__":
    unittest.main()
