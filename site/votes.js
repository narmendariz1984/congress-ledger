// Roll call logic shared by the site and the tests: party splits, decisive votes,
// crossovers, and how members voted. Data comes from data/rollcalls.json (Voteview).
// Each roll call carries `v`, one character per member of that chamber, in the order of
// members[ch]: Y yea, N nay, P present, . not voting, _ not a member at the time.
(function (root) {
  // Votes that decide a bill's fate, not amendments, recommittals or rules
  const DECISIVE = /\b(passage|pass the bill|suspend the rules and (pass|agree)|cloture|motion to proceed|overrid\w*|veto|objections of the president|concur\w*|conference report|discharge|agreeing to the (joint |concurrent )?resolution|on the (joint |concurrent )?resolution|on the bill)\b/i;
  const NOT_DECISIVE = /amendment|recommit|previous question|journal|quorum|adjourn|reconsider|instruct|table(?!.*discharge)|point of order|waive/i;
  const FAILED = /reject|fail|defeat|not (agreed|invoked|sustained|passed)|\bnot\b.*\bpassed\b/i;

  // Concurring in the other chamber's amendment is final passage, so "amendment" doesn't rule it out
  const isDecisive = q => !!q && DECISIVE.test(q) && (!NOT_DECISIVE.test(q) || /\bconcur/i.test(q) && !/recommit|instruct|table|reconsider/i.test(q));
  const failed = res => !!res && FAILED.test(res);

  // Independents (King, Sanders) caucus with Democrats, so they're compared with Democrats
  const side = p => (p === "R" ? "R" : "D");

  function split(rc, members) {
    const t = { D: { Y: 0, N: 0 }, R: { Y: 0, N: 0 }, I: { Y: 0, N: 0 } };
    const v = rc.v || "";
    for (let i = 0; i < v.length; i++) {
      const c = v[i];
      if (c !== "Y" && c !== "N") continue;
      const p = (members[i] || {}).p || "I";
      (t[p] || t.I)[c]++;
    }
    return t;
  }

  // Majority position of each caucus, or null when it's tied
  function majorities(t) {
    const d = { Y: t.D.Y + t.I.Y, N: t.D.N + t.I.N };
    const maj = x => (x.Y > x.N ? "Y" : x.N > x.Y ? "N" : null);
    return { D: maj(d), R: maj(t.R) };
  }

  // Members who voted with the other party's majority when the two parties' majorities split
  function crossovers(rc, members) {
    const m = majorities(split(rc, members));
    if (!m.D || !m.R || m.D === m.R) return [];
    const out = [], v = rc.v || "";
    for (let i = 0; i < v.length; i++) {
      const c = v[i];
      if (c !== "Y" && c !== "N") continue;
      const mem = members[i];
      if (!mem) continue;
      if (c !== m[side(mem.p)]) out.push({ i, mem, vote: c === "Y" ? "Yea" : "Nay" });
    }
    return out;
  }

  const VOTE_WORD = { Y: "Yea", N: "Nay", P: "Present", ".": "Didn't vote", _: "Not in office" };
  const voteOf = (rc, i) => VOTE_WORD[(rc.v || "")[i] || "_"];

  // "HR7567" -> "119-hr7567", the id bills use in ledger.json
  const billId = (m, congress) => (m ? `${congress}-${String(m).toLowerCase().replace(/\s+/g, "")}` : "");

  const api = { isDecisive, failed, split, majorities, crossovers, voteOf, billId, VOTE_WORD };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.RC = api;
})(this);
