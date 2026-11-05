// Roll call logic: decisive votes, party splits, crossovers. Run: node --test tests/votes.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync, existsSync } from "node:fs";

const require = createRequire(import.meta.url);
const RC = require("../site/votes.js");

test("decisive votes are the ones that decide a bill", () => {
  for (const q of ["On Passage", "On Motion to Suspend the Rules and Pass, as Amended", "On the Cloture Motion",
    "On Cloture on the Motion to Proceed", "On the Motion to Proceed", "On Overriding the Veto",
    "On Motion to Concur in the Senate Amendment", "On Passage of the Bill", "On the Joint Resolution",
    "On the Motion (Motion to Discharge S.J.Res. 104)", "On Agreeing to the Conference Report"])
    assert.ok(RC.isDecisive(q), q);
  for (const q of ["On Motion to Recommit", "On Agreeing to the Amendment", "On Ordering the Previous Question",
    "On Motion to Table", "On the Amendment", "Call of the House", "On Motion to Instruct Conferees", "On the Motion to Reconsider"])
    assert.ok(!RC.isDecisive(q), q);
  assert.ok(RC.isDecisive("On the Motion to Table (Motion to Table the Motion to Discharge)"));
});

test("failed results", () => {
  for (const r of ["Cloture Motion Rejected", "Failed", "Motion to Proceed Rejected", "Joint Resolution Defeated", "Bill Defeated", "Cloture on the Motion to Proceed Rejected"])
    assert.ok(RC.failed(r), r);
  for (const r of ["Passed", "Bill Passed", "Cloture Motion Agreed to", "Agreed to", "Motion to Table Agreed to"])
    assert.ok(!RC.failed(r), r);
});

const members = [
  { n: "A Dem", p: "D", s: "MN" }, { n: "B Dem", p: "D", s: "MN" }, { n: "C Dem", p: "D", s: "NY" },
  { n: "D Rep", p: "R", s: "KY" }, { n: "E Rep", p: "R", s: "TX" }, { n: "F Rep", p: "R", s: "TX" },
  { n: "G Ind", p: "I", s: "VT" },
];

test("party split counts yeas and nays by party", () => {
  const t = RC.split({ v: "YYN.NNY" }, members);
  assert.deepEqual(t, { D: { Y: 2, N: 1 }, R: { Y: 0, N: 2 }, I: { Y: 1, N: 0 } });
});

test("crossovers: voting with the other party when the parties split", () => {
  // Dems mostly yea, Reps mostly nay; C Dem voted nay, D Rep voted yea
  const x = RC.crossovers({ v: "YYNYNNY" }, members);
  assert.deepEqual(x.map(c => [c.mem.n, c.vote]), [["C Dem", "Nay"], ["D Rep", "Yea"]]);
});

test("no crossovers when both parties' majorities agree (a 400-10 vote)", () => {
  assert.deepEqual(RC.crossovers({ v: "YYNYYNY" }, members), []);
});

test("independents count with Democrats", () => {
  // Dems split 1-1 plus the independent's yea gives a Democratic yea majority
  const x = RC.crossovers({ v: "YN_NNN Y".replace(" ", "") }, members);
  assert.deepEqual(x.map(c => c.mem.n), ["B Dem"]);
});

test("vote words and bill ids", () => {
  assert.equal(RC.voteOf({ v: "YN._P" }, 2), "Didn't vote");
  assert.equal(RC.voteOf({ v: "YN._P" }, 3), "Not in office");
  assert.equal(RC.voteOf({ v: "YN" }, 9), "Not in office");
  assert.equal(RC.billId("HR7567", 119), "119-hr7567");
  assert.equal(RC.billId("SJRES197", 119), "119-sjres197");
});

test("real data, when present: every vote string matches its chamber's member list", () => {
  const p = new URL("../site/data/rollcalls.json", import.meta.url);
  if (!existsSync(p)) return;
  const R = JSON.parse(readFileSync(p, "utf8"));
  for (const v of R.votes) {
    const n = (R.members[v.ch] || []).length;
    assert.ok(v.v === "" || v.v.length === n, `${v.ch} roll ${v.r}: ${v.v.length} vs ${n} members`);
  }
});
