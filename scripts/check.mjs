// Data quality check, run after every refresh (see .github/workflows/refresh.yml).
// Warnings show in the run's summary and log; serious problems fail the run, so
// GitHub sends a notification. Usage: node scripts/check.mjs [path/to/ledger.json]
import { readFileSync, appendFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const N = require("../site/names.js");
const path = process.argv[2] || new URL("../site/data/ledger.json", import.meta.url);
const RAW = /^(A|An) (bill|joint resolution|concurrent resolution|executive resolution|resolution)\b/i;

const warn = [], err = [];
let L;
try {
  L = JSON.parse(readFileSync(path, "utf8"));
} catch (e) {
  err.push(`ledger.json can't be read: ${e.message}`);
}

if (L) {
  const bills = L.bills || [];
  const congress = L.congress || 119;
  if (bills.length < 50) err.push(`only ${bills.length} bills (expected hundreds); discovery or the API may be failing`);

  // bills: every one needs a number, a title and a readable name
  const ids = new Set(), badNames = [];
  for (const b of bills) {
    if (ids.has(b.id)) warn.push(`duplicate bill ${b.id}`);
    ids.add(b.id);
    if (!b.num || !b.title) warn.push(`${b.id}: missing ${!b.num ? "number" : "title"}`);
    const n = N.nameOf(b.title);
    if (!n || RAW.test(n) || /congressional disapproval under chapter 8/i.test(n) || /&#\d+;|<a /.test(n)) badNames.push(`${b.num}: "${n}"`);
  }

  // votes: readable codes and names; House rows need a question and a tally
  const house = L.votes?.house || [], senate = L.votes?.senate || [];
  const unreadable = [], noTally = [], bareType = [];
  for (const v of [...senate, ...house]) {
    if (v.measure && !N.measureInfo(v.measure, congress)) unreadable.push(`${v.ch} ${v.measure}`);
    if (v.title) {
      const mi = N.measureInfo(v.measure, congress);
      const n = mi && mi.type === "PN" ? N.nomName(v.title) : N.nameOf(N.plain(v.title));
      if (!n || RAW.test(n) || /&#\d+;/.test(n)) badNames.push(`vote ${v.measure}: "${n}"`);
    }
  }
  for (const v of house) {
    const quorum = /quorum|call of the house/i.test(`${v.q} ${v.type || ""}`);
    if (!quorum && !(+v.y || +v.n_)) noTally.push(`roll ${v.n}`);
    if (/^(2\/3 )?yea-and-nay$|^recorded vote$/i.test(v.q || "")) bareType.push(`roll ${v.n}`);
  }

  if (badNames.length) (badNames.length > 10 ? err : warn).push(`${badNames.length} names still read like raw official titles: ${badNames.slice(0, 8).join("; ")}`);
  if (unreadable.length) warn.push(`${unreadable.length} vote codes the site can't read: ${unreadable.slice(0, 8).join(", ")}`);
  if (house.length && noTally.length > house.length / 4) err.push(`${noTally.length} of ${house.length} House votes have no tally; the House vote endpoint may have changed`);
  else if (noTally.length) warn.push(`${noTally.length} House votes have no tally: ${noTally.slice(0, 8).join(", ")}`);
  if (bareType.length) warn.push(`${bareType.length} House votes show only the vote type, not the question: ${bareType.slice(0, 8).join(", ")}`);
  if (!senate.length) warn.push("no Senate votes; Voteview may be unreachable");
  if (!house.length) warn.push("no House votes; the House vote endpoint may be unreachable");

  // What to watch (meta.watch, hand-edited in data/curated.json)
  const W = L.meta?.watch || [];
  const today = new Date().toISOString().slice(0, 10);
  for (const e of W) {
    if (!e.id || !e.title) warn.push(`What to watch: an item is missing its id or title`);
    if (e.date && !/^\d{4}-\d{2}-\d{2}$/.test(e.date)) warn.push(`What to watch: ${e.id} has an unreadable date "${e.date}"`);
    if (!e.date && !e.when) warn.push(`What to watch: ${e.id} has neither a date nor a "when"`);
    if (!(e.src || []).length) warn.push(`What to watch: ${e.id} has no sources`);
  }
  if (W.length && !W.some(e => !e.date || (e.end || e.date) >= today)) warn.push("What to watch: every date has passed; add the next ones to data/curated.json");

  // Vehicle swaps (data/vehicles.json, hand-edited): each listed bill should be on the site
  let VJ = null;
  try { VJ = JSON.parse(readFileSync(new URL("../data/vehicles.json", import.meta.url), "utf8")); } catch { warn.push("data/vehicles.json is missing or isn't valid JSON"); }
  for (const e of VJ?.vehicles || []) {
    const b = bills.find(x => x.id === e.bill);
    if (!b) warn.push(`vehicles.json lists ${e.bill}, but it isn't on the site yet`);
    else if (!b.vehicle) warn.push(`${b.num} is listed in vehicles.json but has no vehicle note`);
  }

  // Roll calls with member votes (site/data/rollcalls.json, from Voteview)
  // it sits next to ledger.json
  const rp = typeof path === "string" ? path.replace(/[^/\\]*$/, "rollcalls.json") : new URL("rollcalls.json", path);
  let RCJ = null;
  try { RCJ = JSON.parse(readFileSync(rp, "utf8")); } catch { warn.push("rollcalls.json is missing or unreadable; the Votes tab falls back to recent votes"); }
  if (RCJ) {
    const bad = (RCJ.votes || []).filter(v => v.v && v.v.length !== (RCJ.members?.[v.ch] || []).length);
    if (bad.length) err.push(`${bad.length} roll calls have member votes that don't line up with the member list`);
    for (const ch of ["H", "S"]) {
      const vs = (RCJ.votes || []).filter(v => v.ch === ch);
      if (!vs.length) warn.push(`rollcalls.json has no ${ch === "H" ? "House" : "Senate"} roll calls`);
      const latest = vs.reduce((m, v) => (v.d > m ? v.d : m), "");
      const ledgerLatest = (ch === "H" ? house : senate).reduce((m, v) => (v.d > m ? v.d : m), "");
      if (latest && ledgerLatest && (Date.parse(ledgerLatest) - Date.parse(latest)) / 864e5 > 7)
        warn.push(`Voteview's ${ch === "H" ? "House" : "Senate"} roll calls end ${latest}, over a week behind Congress.gov (${ledgerLatest})`);
    }
  }

  const age = (Date.now() - Date.parse(L.generatedAt || 0)) / 36e5;
  if (age > 72) warn.push(`data last written ${Math.round(age)} hours ago`);
  if (L.outage?.since) warn.push(`the site is showing an outage note: Congress.gov hasn't responded since ${L.outage.since}`);
  for (const w of L.warnings || []) warn.push(`from the refresh: ${w}`);
}

// report
const lines = [
  `## Data check: ${err.length ? "problems found" : warn.length ? "passed with warnings" : "passed"}`,
  L ? `${(L.bills || []).length} bills, ${(L.votes?.senate || []).length} Senate and ${(L.votes?.house || []).length} House votes` : "",
  ...err.map(e => `- **Error:** ${e}`),
  ...warn.map(w => `- Warning: ${w}`),
];
console.log(lines.join("\n"));
for (const e of err) console.log(`::error title=Data check::${e}`);
for (const w of warn.slice(0, 20)) console.log(`::warning title=Data check::${w}`);
if (process.env.GITHUB_STEP_SUMMARY) appendFileSync(process.env.GITHUB_STEP_SUMMARY, lines.join("\n") + "\n");
process.exit(err.length ? 1 : 0);
