// Naming, measure codes and state search, checked against real cases.
// Run: node --test tests/
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync, existsSync } from "node:fs";

const require = createRequire(import.meta.url);
const N = require("../site/names.js");

const RAW = /^(A|An) (bill|joint resolution|concurrent resolution|executive resolution|resolution)\b/i;

test("short titles pass through unchanged", () => {
  assert.equal(N.nameOf("Laken Riley Act"), "Laken Riley Act");
  assert.equal(N.nameOf("One Big Beautiful Bill Act"), "One Big Beautiful Bill Act");
});

test("rule-overturning resolutions (Congressional Review Act)", () => {
  assert.equal(
    N.nameOf('Providing for congressional disapproval under chapter 8 of title 5, United States Code, of the rule submitted by the Bureau of Land Management relating to "Buffalo Field Office Record of Decision and Approved Resource Management Plan Amendment".'),
    "Overturn BLM rule: Buffalo Field Office Record of Decision and…");
  // Senate wording, "issued by", and the Energy Dept. sub-office
  assert.match(N.nameOf('A joint resolution providing for congressional disapproval under chapter 8 of title 5, United States Code, of the rule submitted by the Bureau of Ocean Energy Management relating to "Protection of Marine Archaeological Resources".'), /^Overturn BOEM rule: Protection of Marine/);
  assert.match(N.nameOf('Providing for congressional disapproval under chapter 8 of title 5, United States Code, of the rule issued by the Environmental Protection Agency relating to the "California State Nonroad Engine Pollution Control Standards".'), /^Overturn EPA rule: California State Nonroad/);
  assert.match(N.nameOf('Providing for congressional disapproval under chapter 8 of title 5, United States Code, of the rule submitted by the Office of Energy Efficiency and Renewable Energy, Department of Energy relating to "Energy Conservation Program: Energy Conservation Standards for Commercial Refrigerators".'), /^Overturn Energy Dept\. rule: Energy Conservation Standards for/);
});

test("S.J.Res. 197: Voteview cuts the title off mid-word and encodes the ampersand", () => {
  const t = "A joint resolution providing for congressional disapproval under chapter 8 of title 5, United States Code, of the rule submitted by the Centers for Medicare &#38; Medicaid Services of the Department of Health and Human Servi";
  assert.equal(N.nameOf(t), "Overturn CMS rule");
});

test("war powers resolutions, House and Senate wording", () => {
  assert.equal(N.nameOf("A concurrent resolution directing the President, pursuant to section 5(c) of the War Powers Resolution, to remove United States Armed Forces from hostilities with Iran."),
    "War powers: remove U.S. forces from hostilities with Iran");
  assert.match(N.nameOf("A joint resolution to direct the removal of United States Armed Forces from hostilities within or against Venezuela that have not been authorized by Congress."),
    /^War powers: remove U\.S\. forces from hostilities within or against/);
});

test("other resolution patterns", () => {
  assert.equal(N.nameOf("A joint resolution providing for congressional disapproval of the proposed foreign military sale to Israel of certain defense articles and services."), "Block proposed arms sale to Israel");
  assert.equal(N.nameOf("A joint resolution providing for congressional disapproval of the proposed export of certain defense articles to Israel."), "Block proposed arms export to Israel");
  assert.equal(N.nameOf("A joint resolution terminating the national emergency declared to impose global tariffs."), "End the national emergency declared to impose global tariffs");
  assert.equal(N.nameOf("Proposing an amendment to the Constitution of the United States requiring a balanced budget for the Federal Government."), "Constitutional amendment requiring a balanced budget for the Federal…");
  assert.match(N.nameOf("Disapproving the action of the District of Columbia Council in approving the D.C. Income and Franchise Tax Conformity and Revision Temporary Amendment Act of 2025."), /^Block D\.C\. law: /);
  assert.equal(N.nameOf("Providing for consideration of the bill (H.R. 1501) to amend title 18, United States Code, and for other purposes."), "Rule for debating H.R. 1501");
  assert.equal(N.nameOf("A resolution requesting information on Israel's human rights practices."), "Requesting information on Israel's human rights practices");
});

test("plain bills and tidy endings", () => {
  assert.match(N.nameOf("A bill to require the Federal Energy Regulatory Commission to extend the time period during which licensees are required to commence construction."), /^To require the Federal Energy Regulatory Commission to extend the…$/);
  assert.equal(N.nameOf("Expressing support for tax policies that support working families."), "Expressing support for tax policies that support working families");
  assert.ok(N.nameOf("x ".repeat(80)).length <= 72);
});

test("nominations", () => {
  assert.equal(N.nomName("Keith Sonderling, of Florida, to be Secretary of Labor"), "Keith Sonderling to be Secretary of Labor");
  assert.match(N.nomName("Angela Veronica Colmenero, of Texas, to be United States District Judge for the Southern District of Texas"),
    /^Angela Veronica Colmenero to be U\.S\. District Judge for the Southern District/);
  assert.equal(N.nomName("Walter Clayton, of New York, to be Director of National Intelligence, vice John Doe"), "Walter Clayton to be Director of National Intelligence");
});

test("measure codes and Congress.gov links", () => {
  assert.deepEqual(N.measureInfo("SRES852", 119), { type: "SRES", num: "852", label: "S.Res. 852", url: "https://www.congress.gov/bill/119th-congress/senate-resolution/852" });
  assert.equal(N.measureInfo("HCONRES 89", 119).label, "H.Con.Res. 89");
  assert.equal(N.measureInfo("HJRES 210", 119).url, "https://www.congress.gov/bill/119th-congress/house-joint-resolution/210");
  assert.equal(N.measureInfo("PN1129", 119).url, "https://www.congress.gov/nomination/119th-congress/1129");
  assert.equal(N.measureInfo("H.R. 131", 119).label, "H.R. 131");
  assert.equal(N.measureInfo("", 119), null);
  assert.equal(N.measureInfo("XYZ 5", 119), null);
});

test("state search", () => {
  assert.deepEqual(N.stateQuery("MN"), { st: "MN" });
  assert.deepEqual(N.stateQuery("mn"), { st: "MN" });
  assert.deepEqual(N.stateQuery("Minnesota"), { st: "MN" });
  assert.deepEqual(N.stateQuery("new york"), { st: "NY" });
  assert.deepEqual(N.stateQuery("MN-5"), { st: "MN", dist: "5" });
  assert.deepEqual(N.stateQuery("in"), { st: "IN" });
  assert.equal(N.stateQuery("amendment"), null);
  assert.equal(N.stateQuery("Laken"), null);
});

test("entities and HTML are cleaned", () => {
  assert.equal(N.decodeEnt("Medicare &#38; Medicaid &amp; more"), "Medicare & Medicaid & more");
  assert.equal(N.plain('Petition No: 119-16. (<a href="https://clerk.house.gov/x">Discharge petition</a> text)'), "Petition No: 119-16. (Discharge petition text)");
});

// Every real title in the current data must come out readable.
test("every bill and vote in the current data gets a readable name", () => {
  const p = new URL("../site/data/ledger.json", import.meta.url);
  if (!existsSync(p)) return;
  const L = JSON.parse(readFileSync(p, "utf8"));
  const bad = [];
  for (const b of L.bills || []) {
    const n = N.nameOf(b.title);
    if (!n || RAW.test(n) || /congressional disapproval under chapter 8/i.test(n) || /&#\d+;|<a /.test(n) || n.length > 81) bad.push(`${b.num}: ${n}`);
  }
  for (const v of [...(L.votes?.senate || []), ...(L.votes?.house || [])]) {
    if (!v.title) continue;
    const mi = N.measureInfo(v.measure, 119);
    const n = mi && mi.type === "PN" ? N.nomName(v.title) : N.nameOf(N.plain(v.title));
    if (!n || RAW.test(n) || /&#\d+;/.test(n)) bad.push(`${v.measure}: ${n}`);
  }
  assert.deepEqual(bad, []);
});
