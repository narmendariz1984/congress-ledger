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
  assert.deepEqual(t, { D: { Y: 2, N: 1, P: 0, X: 0 }, R: { Y: 0, N: 2, P: 0, X: 1 }, I: { Y: 1, N: 0, P: 0, X: 0 } });
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

// ---- What happened: floor decisions for What to watch ----
const vote = (o) => ({ ch: "H", n: 317, d: "2026-11-10", q: "On Motion to Refer", result: "Passed", y: "211", n_: "204", measure: "HRES 1655",
  title: "Impeaching Peter Brian Hegseth, Secretary of Defense, for high crimes and misdemeanors", ...o });

test("decisions: impeachment, censure, expulsion and war powers votes are always in", () => {
  assert.equal(RC.notable(vote()), "special");
  assert.equal(RC.headline(vote(), RC.subject(vote().title)), "House sends Hegseth impeachment resolution to committee, 211–204");
  const tabled = vote({ q: "On Motion to Table", y: "232", n_: "147", title: "Impeaching Donald John Trump, President of the United States, for high crimes" });
  assert.equal(RC.headline(tabled, RC.subject(tabled.title)), "House tables Trump impeachment resolution, 232–147");
  const censure = vote({ q: "On Agreeing to the Resolution", y: "224", n_: "198", measure: "HRES 189", title: "Censuring Representative Al Green of Texas" });
  assert.equal(RC.headline(censure, RC.subject(censure.title)), "House censures Rep. Al Green, 224–198");
  const failedCensure = vote({ q: "On Agreeing to the Resolution", result: "Failed", y: "209", n_: "214", measure: "HRES 888",
    title: "Censuring and condemning Delegate Stacey Plaskett and removing her from the Permanent Select Committee" });
  assert.equal(RC.headline(failedCensure, RC.subject(failedCensure.title)), "House rejects censure of Del. Stacey Plaskett, 209–214");
  const wp = { ch: "S", n: 240, d: "2026-09-24", q: "On the Concurrent Resolution", result: "Concurrent Resolution Rejected", y: 49, no: 50, m: "HCONRES89",
    t: "A concurrent resolution directing the President, pursuant to section 5(c) of the War Powers Resolution, to remove United States Armed Forces from hostilities against the Islamic Republic of Iran that have not been authorized by Congress." };
  assert.equal(RC.headline(wp, RC.subject(wp.t)), "Senate rejects Iran war powers resolution, 49–50");
});

test("decisions: the rule that sets up a debate is not a decision", () => {
  assert.equal(RC.notable(vote({ q: "On Agreeing to the Resolution", measure: "HRES 1650", title: "Providing for consideration of the bill (H.R. 1013)" })), null);
});

test("decisions: close passage is in, lopsided passage is out", () => {
  const close = vote({ q: "On Passage", measure: "HR 10326", title: "PROOF Act", y: "217", n_: "207" });
  assert.equal(RC.notable(close), "close");
  assert.equal(RC.headline(close, "PROOF Act"), "House passes PROOF Act, 217–207");
  assert.equal(RC.notable(vote({ q: "On Motion to Suspend the Rules and Pass", measure: "HR 9612", title: "American Enrichment Deployment Act", y: "394", n_: "3" })), null);
});

test("decisions: a bill that fails is in, however lopsided", () => {
  const f = vote({ q: "On Passage", result: "Failed", measure: "HR 1329", title: "Smithsonian American Women's History Museum Act", y: "204", n_: "216" });
  assert.equal(RC.notable(f), "failed");
  assert.equal(RC.headline(f, "Smithsonian American Women's History Museum Act"), "House rejects Smithsonian American Women's History Museum Act, 204–216");
});

test("decisions: Senate cloture on legislation, not on nominations", () => {
  const c = { ch: "S", n: 257, d: "2026-11-09", q: "On Cloture on the Motion to Proceed", result: "Cloture on the Motion to Proceed Agreed to", y: 73, no: 25, m: "HR2347", t: "A bill to amend the tax code" };
  assert.equal(RC.notable(c), "cloture");
  assert.equal(RC.headline(c, "Bipartisan American Affordability and Jobs Act (in H.R. 2347)"), "Senate advances Bipartisan American Affordability and Jobs Act (in H.R. 2347), 73–25");
  assert.equal(RC.headline({ ...c, result: "Cloture on the Motion to Proceed Rejected", y: 57, no: 43 }, "Ratepayer Protection Act"), "Senate fails to advance Ratepayer Protection Act, 57–43");
  assert.equal(RC.notable({ ...c, m: "PN117", q: "On the Cloture Motion" }), null);
});

test("decisions: veto overrides, joint resolutions pass and concurrence names the other chamber", () => {
  const ov = vote({ q: "Passage, Objections of the President To The Contrary Notwithstanding", result: "Failed", measure: "HR 131", title: "Finish the Arkansas Valley Conduit Act", y: "248", n_: "177" });
  assert.equal(RC.notable(ov), "veto");
  assert.equal(RC.headline(ov, "Finish the Arkansas Valley Conduit Act"), "House fails to override veto of Finish the Arkansas Valley Conduit Act, 248–177");
  const jr = vote({ q: "On Passage", measure: "HJRES 213", title: "Providing for congressional disapproval", y: "214", n_: "208" });
  assert.equal(RC.headline(jr, RC.subject(jr.title, "Overturn EPA rule: Nonroad Engines")), "House passes resolution to overturn EPA rule: Nonroad Engines, 214–208");
  const cc = vote({ q: "On Motion to Concur in the Senate Amendments", measure: "HR 5334", title: "X", y: "262", n_: "159" });
  assert.equal(RC.headline(cc, "Early Educators Act"), "House accepts the Senate version of Early Educators Act, 262–159");
});

test("decisions: one line per measure per day, newest first, and bad records are skipped", () => {
  const a = vote({ n: 1, q: "On Motion to Refer", result: "Failed", y: "213", n_: "214", measure: "HRES 888", title: "Censuring and condemning Delegate Stacey Plaskett and removing her" });
  const b = { ...a, n: 2, q: "On Agreeing to the Resolution", y: "209", n_: "214" };
  const out = RC.decisions([a, b, null, {}, { d: "2026-01-01" }, vote({ d: "2026-11-11", n: 320 })], () => "");
  assert.deepEqual(out.map(x => x.v.n), [320, 2]);
  assert.equal(out[1].h, "House rejects censure of Del. Stacey Plaskett, 209–214");
});

test("plain words for what a motion did", () => {
  assert.equal(RC.explain(vote()), "The House voted to send it to committee instead of voting on it directly. It dies there unless the committee acts before this Congress ends Jan 3, 2027.");
  assert.equal(RC.explain(vote({ result: "Failed" })), "A motion to send it to committee failed, so it stayed on the House floor.");
  assert.equal(RC.explain(vote({ q: "On Motion to Table", d: "2025-06-24" })), "The House voted to set it aside without voting on it directly, which in practice ends it for this Congress.");
  assert.equal(RC.explain(vote({ d: "2025-11-19" })).endsWith("ends Jan 3, 2027."), true);
  const c = { ch: "S", d: "2026-11-09", q: "On Cloture on the Motion to Proceed", result: "Cloture on the Motion to Proceed Agreed to" };
  assert.equal(RC.explain(c), "The Senate voted to end debate on taking it up so it can move forward. Ending debate takes 60 votes.");
  assert.equal(RC.explain({ ...c, result: "Cloture on the Motion to Proceed Rejected" }), "The Senate fell short of the 60 votes needed to end debate on taking it up, so it's blocked for now.");
  assert.equal(RC.explain(vote({ q: "Passage, Objections of the President To The Contrary Notwithstanding", result: "Failed" })), "It fell short of the two-thirds needed to override, so the veto stands.");
  assert.equal(RC.explain(vote({ q: "On Motion to Concur in the Senate Amendments" })), "Both chambers have now passed the same text, so it goes to the President.");
  assert.equal(RC.explain(vote({ q: "On Passage" })), "");
});

test("every member accounted for: present and didn't vote, by party", () => {
  const t = RC.fromTotals({ D: [0, 203, 0, 11], R: [210, 1, 1, 8], I: [1, 0, 0, 0] });
  assert.equal(RC.partyText(t), "D 0–203, 11 didn't vote · R 210–1, 1 present, 8 didn't vote · I 1–0");
  assert.equal(RC.partyText(RC.fromTotals({ D: [5, 1], R: [3, 2] })), "D 5–1 · R 3–2");  // no independents, nothing extra
  assert.equal(RC.partyText(RC.split({ v: "YYN.NNY" }, members)), "D 2–1 · R 0–2, 1 didn't vote · I 1–0");
  assert.equal(RC.partyText(null), "");
});

test("the page asks for the current version of each shared script", () => {
  // index.html loads names.js?v=<hash> and votes.js?v=<hash>; a stale hash would let browsers run
  // an old cached copy with a new page. Update the ?v= value whenever these files change.
  const { createHash } = require("node:crypto");
  const html = readFileSync(new URL("../site/index.html", import.meta.url), "utf8");
  for (const f of ["names.js", "votes.js"]) {
    const want = createHash("sha256").update(readFileSync(new URL(`../site/${f}`, import.meta.url))).digest("hex").slice(0, 8);
    assert.match(html, new RegExp(`<script src="${f}\\?v=${want}"></script>`), `${f}: update its ?v= in index.html to ${want}`);
  }
});
