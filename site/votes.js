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

  // Everyone in each party: yea, nay, present (P) and didn't vote (X). "_" was not a member then.
  function split(rc, members) {
    const t = { D: { Y: 0, N: 0, P: 0, X: 0 }, R: { Y: 0, N: 0, P: 0, X: 0 }, I: { Y: 0, N: 0, P: 0, X: 0 } };
    const v = rc.v || "";
    for (let i = 0; i < v.length; i++) {
      const c = v[i] === "." ? "X" : v[i];
      if (!"YNPX".includes(c)) continue;
      const p = (members[i] || {}).p || "I";
      (t[p] || t.I)[c]++;
    }
    return t;
  }

  // The House Clerk's party totals ({R: [yea, nay, present, not voting], ...}) in the same shape
  function fromTotals(p) {
    const one = a => ({ Y: +(a || [])[0] || 0, N: +(a || [])[1] || 0, P: +(a || [])[2] || 0, X: +(a || [])[3] || 0 });
    return p && p.R && p.D ? { D: one(p.D), R: one(p.R), I: one(p.I) } : null;
  }

  // "D 0–203, 11 didn't vote · R 210–1, 8 didn't vote · I 1–0": every member accounted for
  function partyParts(t) {
    if (!t) return [];
    return ["D", "R", "I"].map(k => {
      const x = t[k];
      if (!x || (k === "I" && !(x.Y || x.N || x.P || x.X))) return null;
      const extra = [x.P ? `${x.P} present` : "", x.X ? `${x.X} didn't vote` : ""].filter(Boolean).join(", ");
      return { p: k, s: `${k} ${x.Y || 0}–${x.N || 0}${extra ? `, ${extra}` : ""}` };
    }).filter(Boolean);
  }
  const partyText = t => partyParts(t).map(x => x.s).join(" · ");

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

  // ---- What happened: floor decisions worth a line on What to watch, with a plain headline ----
  // Kept tight on purpose: impeachment, censure, expulsion, contempt and war powers votes; veto
  // overrides; bills that fail; Senate cloture on legislation; and close passage votes (the losing
  // side has at least 40%). Lopsided passage votes, nominations and procedural votes stay out.
  const SPECIAL = /\bimpeach|\bcensur|\bexpel|\bexpulsion|contempt of congress|office of speaker|vacat\w* the (office|chair)|war powers/i;
  const DISPOSE = /passage|pass the bill|suspend the rules and pass|agreeing to the (joint |concurrent )?resolution|on the (joint |concurrent )?resolution|motion to (lay (it )?on the )?table|motion to refer|motion to postpone|concur|conference report|objections of the president|overrid/i;
  const FINAL = /\bon passage|passage of the bill|suspend the rules and pass|pass the bill|\bconcur\b|conference report|on the joint resolution|agreeing to the joint resolution|\bon the bill\b/i;
  const VETO = /objections of the president|overrid/i;
  const RULE = /providing for (the )?consideration/i;
  const OK = res => /agreed|passed|confirmed|invoked|sustained/i.test(res || "") && !/\bnot\b|rejected|failed/i.test(res || "");
  const code = v => String(v.measure || v.m || "").replace(/\s+/g, "").toUpperCase();

  function notable(v) {
    if (!v || !v.d) return null;
    const q = v.q || "", m = code(v), t = v.title || v.t || "";
    if (/^HRES/.test(m) && RULE.test(t)) return null;
    if (SPECIAL.test(t) && DISPOSE.test(q)) return "special";
    if (VETO.test(q)) return "veto";
    if (/^PN/.test(m)) return null;
    if (/cloture/i.test(q)) return v.ch === "S" && /^(HR|S|HJRES|SJRES)\d/.test(m) ? "cloture" : null;
    if (FINAL.test(q) && /^(HR|S|HJRES|SJRES)\d/.test(m)) {
      if (!OK(v.result || v.res)) return "failed";
      const y = +v.y || 0, n = +(v.n_ != null ? v.n_ : v.no) || 0;
      if (y + n && Math.min(y, n) / (y + n) >= 0.4) return "close";
    }
    return null;
  }

  // What the vote was about, short enough for a headline
  function subject(t, fallback) {
    t = String(t || "");
    let m;
    if ((m = /^Impeaching (.+?)(?:,| for high)/i.exec(t))) return `${m[1].trim().split(/\s+/).pop()} impeachment resolution`;
    if ((m = /^Censuring (?:and condemning )?(Representative|Delegate|Resident Commissioner) (.+?)(?: of [A-Z][\w .]+?)?(?: and |,|$)/i.exec(t)))
      return `censure of ${{ representative: "Rep.", delegate: "Del." }[m[1].toLowerCase()] || "Res. Comm."} ${m[2].trim()}`;
    if ((m = /^Expelling (?:Representative )?(.+?)(?: from|,|$)/i.exec(t))) return `expulsion of Rep. ${m[1].trim()}`;
    if (/war powers/i.test(t)) {
      m = /hostilities (?:against|in|within|with) (?:the )?(.+?)(?: that| which| not|,|\.|;|$)/i.exec(t);
      const where = m ? m[1].replace(/^Islamic Republic of /i, "").replace(/^Bolivarian Republic of /i, "").trim() : "";
      return where ? `${where} war powers resolution` : "war powers resolution";
    }
    if (/^Overturn /.test(fallback || "")) return `resolution to overturn ${fallback.slice(9)}`;
    return fallback;
  }

  // "House sends Hegseth impeachment resolution to committee, 211–204"
  function headline(v, subj) {
    const ch = v.ch === "S" ? "Senate" : "House", q = v.q || "", ok = OK(v.result || v.res);
    const tally = `${+v.y || 0}–${+(v.n_ != null ? v.n_ : v.no) || 0}`;
    let h;
    if (/motion to (lay (it )?on the )?table/i.test(q)) h = ok ? `${ch} tables ${subj}` : `${ch} refuses to table ${subj}`;
    else if (/motion to refer/i.test(q)) h = ok ? `${ch} sends ${subj} to committee` : `${ch} refuses to send ${subj} to committee`;
    else if (/motion to postpone/i.test(q)) h = ok ? `${ch} postpones ${subj}` : `${ch} refuses to postpone ${subj}`;
    else if (VETO.test(q)) h = ok ? `${ch} overrides veto of ${subj}` : `${ch} fails to override veto of ${subj}`;
    else if (/cloture/i.test(q)) h = ok ? `${ch} advances ${subj}` : `${ch} fails to advance ${subj}`;
    else if (/^censure of /.test(subj) && ok) h = `${ch} censures ${subj.replace(/^censure of /, "")}`;
    else if (/^expulsion of /.test(subj) && ok) h = `${ch} expels ${subj.replace(/^expulsion of /, "")}`;
    else if (/impeachment resolution$/.test(subj) && ok) h = `${ch} impeaches ${subj.replace(/ impeachment resolution$/, "")}`;
    else if (/\bconcur\b/i.test(q)) h = ok ? `${ch} accepts the ${ch === "House" ? "Senate" : "House"} version of ${subj}` : `${ch} rejects the ${ch === "House" ? "Senate" : "House"} version of ${subj}`;
    else if (/^(HRES|HCONRES|SRES|SCONRES)/.test(code(v)) || / resolution$/.test(subj)) h = ok ? `${ch} adopts ${subj}` : `${ch} rejects ${subj}`;
    else h = ok ? `${ch} passes ${subj}` : `${ch} rejects ${subj}`;
    return `${h}, ${tally}`;
  }

  // What the vote did, in plain words, for motions people don't read every day. Passage needs none.
  function explain(v) {
    const ch = v.ch === "S" ? "Senate" : "House", q = v.q || "", ok = OK(v.result || v.res);
    const y = parseInt(String(v.d || "").slice(0, 4), 10);
    const ends = y ? `Jan 3, ${y % 2 ? y + 2 : y + 1}` : "Jan 3";  // a Congress ends Jan 3 of the next odd year
    if (/motion to refer/i.test(q)) return ok
      ? `The ${ch} voted to send it to committee instead of voting on it directly. It dies there unless the committee acts before this Congress ends ${ends}.`
      : `A motion to send it to committee failed, so it stayed on the ${ch} floor.`;
    if (/motion to (lay (it )?on the )?table/i.test(q)) return ok
      ? `The ${ch} voted to set it aside without voting on it directly, which in practice ends it for this Congress.`
      : `A motion to set it aside failed, so it stayed on the ${ch} floor.`;
    if (/motion to postpone/i.test(q)) return ok ? `The ${ch} voted to put off a decision on it.` : `A motion to put off a decision on it failed.`;
    if (VETO.test(q)) return ok
      ? "It got the two-thirds needed to override. Both the House and Senate have to override for it to become law."
      : "It fell short of the two-thirds needed to override, so the veto stands.";
    if (/cloture/i.test(q)) {
      const what = /motion to proceed/i.test(q) ? "taking it up" : "it";
      return ok ? `The Senate voted to end debate on ${what} so it can move forward. Ending debate takes 60 votes.`
        : `The Senate fell short of the 60 votes needed to end debate on ${what}, so it's blocked for now.`;
    }
    if (/\bconcur\b/i.test(q) && ok) return /with an amendment/i.test(q)
      ? `It goes back to the ${ch === "House" ? "Senate" : "House"} with more changes.`
      : "Both chambers have now passed the same text, so it goes to the President.";
    return "";
  }

  // A bill the House took up under a rule (major or contested bills, which almost always get a
  // recorded vote) that passed by voice vote or without objection, so there's no record of how
  // anyone voted. Routine "suspension" bills that pass by voice vote are not included.
  const RULE_FOR = /^Rules Committee Resolution H\. ?Res\. ?(\d+) Reported to House/i;
  const UNRECORDED = /^(?:Passed\/agreed to in House: )?On passage Passed (by voice vote|without objection)/i;
  function unrecorded(bills) {
    const out = [];
    for (const b of bills || []) {
      try {
        const tl = (b && b.timeline || []).filter(t => t && t.d && t.e).slice().sort((x, y) => x.d.localeCompare(y.d));
        const pass = tl.filter(t => UNRECORDED.test(t.e)).pop();
        const rule = pass && tl.filter(t => t.d <= pass.d && RULE_FOR.test(t.e)).pop();  // the rule that brought it up
        if (!pass || !rule) continue;
        out.push({ id: b.id, d: pass.d.slice(0, 10), how: /without objection/i.test(pass.e) ? "without objection" : "by voice vote", rule: `H.Res. ${RULE_FOR.exec(rule.e)[1]}` });
      } catch (e) { /* a bad record is skipped */ }
    }
    return out;
  }

  // ---- Today: what moved on each bill on a given day, from its actions ----
  const MOVES = [
    ["law", /^Became Public Law|^Signed by President/i],
    ["veto", /^Vetoed by President/i],
    ["failed", /^Failed of passage/i],
    ["passed", /^Passed\/agreed to in (House|Senate)/i],
    ["cloture", /^Cloture on .*?\b(not invoked|invoked)\b in Senate/i],
    ["proceed", /^Motion to proceed to consideration of measure (agreed to|not agreed to|rejected) in Senate/i],
    ["sent", /^Presented to President/i],
  ];
  const RANK = { law: 0, veto: 1, failed: 2, passed: 3, cloture: 4, proceed: 4, sent: 5 };

  function moveOf(e) {
    e = String(e || "");
    const hit = MOVES.find(([, re]) => re.test(e));
    if (!hit) return null;
    const kind = hit[0];
    const ch = /\bin Senate\b|Passed Senate/i.test(e) || kind === "cloture" || kind === "proceed" ? "S" : /\bin House\b/i.test(e) ? "H" : "";
    const pl = /Public Law No:\s*([\d-]+)/i.exec(e);
    const t = /(?<![\d/])(\d{1,3})\s*-\s*(\d{1,3})(?![\d/])/.exec(e);
    const roll = /Roll no\.\s*(\d+)|Record Vote Number:\s*(\d+)/i.exec(e);
    return { kind, ch, y: t ? +t[1] : null, n: t ? +t[2] : null, roll: roll ? +(roll[1] || roll[2]) : null,
      how: /voice vote/i.test(e) ? "voice" : /unanimous consent/i.test(e) ? "uc" : /without objection/i.test(e) ? "uc" : t ? "roll" : "",
      twoThirds: /2\/3 required/i.test(e), mtp: /motion to proceed/i.test(e), pl: pl ? pl[1] : "",
      invoked: (kind === "cloture" && !/not invoked/i.test(e)) || (kind === "proceed" && /agreed to in/i.test(e) && !/not agreed/i.test(e)) };
  }

  // [{ b, moves }] for one day, biggest first: laws, vetoes, failures, passage, cloture; closer votes first
  function dayMoves(bills, day) {
    const out = [];
    for (const b of bills || []) {
      try {
        const seen = new Set(), moves = [];
        for (const t of (b && b.timeline) || []) {
          if (!t || String(t.d).slice(0, 10) !== day) continue;
          const m = moveOf(t.e);
          if (m && !seen.has(m.kind + m.ch)) { seen.add(m.kind + m.ch); moves.push(m); }
        }
        if (moves.length) out.push({ b, moves: moves.sort((x, y) => RANK[x.kind] - RANK[y.kind]) });
      } catch (e) { /* a bad record is skipped */ }
    }
    const close = m => (m.y != null && m.y + m.n ? Math.abs(m.y - m.n) / (m.y + m.n) : 2);
    return out.sort((a, c) => RANK[a.moves[0].kind] - RANK[c.moves[0].kind] || close(a.moves[0]) - close(c.moves[0]) || ((c.b.cosponsors || {}).n || 0) - ((a.b.cosponsors || {}).n || 0));
  }

  // Days that had at least one move, newest first
  function activeDays(bills) {
    const days = new Set();
    for (const b of bills || []) for (const t of (b && b.timeline) || []) if (t && t.d && moveOf(t.e)) days.add(String(t.d).slice(0, 10));
    return [...days].sort().reverse();
  }

  const CH = { H: "House", S: "Senate" };
  function moveText(m) {
    const tally = m.y != null ? `${m.y}–${m.n}` : "";
    if (m.kind === "law") return m.pl ? `Became law (Public Law ${m.pl})` : "Became law";
    if (m.kind === "sent") return "Sent to the President";
    if (m.kind === "proceed") return m.invoked ? (tally ? `Senate voted ${tally} to take it up` : "Senate agreed to take it up") : `Senate voted not to take it up${tally ? `, ${tally}` : ""}`;
    if (m.kind === "veto") return "Vetoed";
    if (m.kind === "failed") return `Failed in the ${CH[m.ch] || "chamber"}${tally ? `, ${tally}` : ""}${m.twoThirds ? " (needed two-thirds)" : ""}`;
    if (m.kind === "cloture") return m.invoked ? `Senate voted ${tally} to end debate${m.mtp ? " on taking it up" : ""}` : `Senate fell short of the 60 votes to end debate, ${tally}`;
    return `Passed the ${CH[m.ch] || "chamber"} ${tally || (m.how === "voice" ? "by voice vote" : m.how === "uc" ? "by unanimous consent" : "")}`.trim();
  }

  // Introduced ▸ House ▸ Senate ▸ President ▸ Law, in the bill's own order; each step done, now, todo or no
  // A vehicle: a bill number one chamber already passed with its old text, reused to carry new text.
  // The new text has to pass the other chamber, then go back to the first one.
  function vehicleRoute(b) {
    const v = b && b.vehicle, op = (v && v.orig && v.orig.passed) || {};
    const first = op.H ? "H" : op.S ? "S" : "";
    if (!first) return null;
    const p = b.passed || {}, since = v.since || "", other = first === "H" ? "S" : "H";
    const after = c => p[c] && (!p[c].d || p[c].d >= since);
    return { first, other, when: (op[first] && op[first].d) || "", otherDone: !!after(other), backDone: !!after(first) };
  }

  function track(b) {
    const vr = vehicleRoute(b);
    if (vr && b.status !== "law" && b.status !== "vetoed" && b.status !== "killed") {
      const steps = [["Introduced", true], [CH[vr.other], vr.otherDone], [`${CH[vr.first]} again`, vr.backDone], ["President", false], ["Law", false]];
      let now = false;
      return steps.map(([k, done]) => done ? { k, s: "done" } : !now ? (now = true, { k, s: "now" }) : { k, s: "todo" });
    }
    const origin = /^S/i.test(String(b.num || "").replace(/[^A-Za-z]/g, "")) ? "S" : "H";
    const p = b.passed || {}, o = b.outcome || {}, law = b.status === "law", veto = b.status === "vetoed";
    const steps = [["Introduced", true], [CH[origin], !!p[origin]], [CH[origin === "H" ? "S" : "H"], !!p[origin === "H" ? "S" : "H"]],
      [veto ? "Vetoed" : "President", law || veto || !!o.pres], ["Law", law]];
    let now = false;
    return steps.map(([k, done]) => {
      if (k === "Vetoed") return { k, s: "no" };
      if (done) return { k, s: "done" };
      if (!now && b.status !== "killed" && !veto) { now = true; return { k, s: "now" }; }
      return { k, s: "todo" };
    });
  }

  // "Is it law?" in plain words
  function lawLine(b) {
    const o = b.outcome || {}, p = b.passed || {}, who = o.pres ? `President ${String(o.pres).split(" ").pop()}` : "the President";
    const when = o.d ? new Date(o.d + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "";
    if (b.status === "law") return /without signature/i.test(o.where || "") ? `Yes. It became law without a signature${when ? ` on ${when}` : ""}.`
      : /over a veto/i.test(o.where || "") ? `Yes. Congress overrode the veto${when ? ` on ${when}` : ""}.` : `Yes. Signed${when ? ` ${when}` : ""} by ${who}.`;
    if (b.status === "vetoed") return `No. Vetoed${when ? ` ${when}` : ""} by ${who}.`;
    if (b.status === "killed") return "No. It failed on the floor.";
    const vr = vehicleRoute(b);
    if (vr) {
      const mo = vr.when ? new Date(vr.when + "T12:00:00").toLocaleDateString("en-US", { month: "long", year: "numeric" }) : "";
      if (vr.otherDone && vr.backDone) return "Not yet. Both chambers passed the new text; the President is next.";
      if (vr.otherDone) return `Not yet. The ${CH[vr.other]} passed the new text; it goes back to the ${CH[vr.first]} next.`;
      return `Not yet. The ${CH[vr.first]} passed this bill number with its old text${mo ? ` in ${mo}` : ""}. If the ${CH[vr.other]} passes the new text, it goes back to the ${CH[vr.first]}.`;
    }
    const origin = /^S/i.test(String(b.num || "").replace(/[^A-Za-z]/g, "")) ? "S" : "H", other = origin === "H" ? "S" : "H";
    if (p[origin] && p[other]) return "Not yet. Both chambers passed it; the President is next.";
    if (p[origin]) return `Not yet. It passed the ${CH[origin]}; the ${CH[other]} is next.`;
    if (p[other]) return `Not yet. It passed the ${CH[other]}; the ${CH[origin]} is next.`;
    return "Not yet. It hasn't passed either chamber.";
  }

  // One line per measure per day: the last notable roll call that day decided it
  function decisions(votes, nameOf) {
    const by = {};
    for (const v of votes || []) {
      let kind;
      try { kind = notable(v); } catch (e) { kind = null; }
      if (!kind) continue;
      const k = `${v.ch}|${code(v) || v.n}|${v.d}`;
      if (!by[k] || (+v.n || 0) > (+by[k].v.n || 0)) by[k] = { v, kind };
    }
    return Object.values(by).map(({ v, kind }) => {
      const name = subject(v.title || v.t, (nameOf && nameOf(v)) || code(v));
      return { id: `v-${v.ch}-${String(v.d).slice(0, 4)}-${v.n}`, date: v.d, kind, v, h: headline(v, name) };
    }).sort((a, b) => b.date.localeCompare(a.date) || (+b.v.n || 0) - (+a.v.n || 0));
  }

  const api = { isDecisive, failed, split, majorities, crossovers, voteOf, billId, VOTE_WORD, notable, subject, headline, explain, decisions, fromTotals, partyParts, partyText, unrecorded, moveOf, dayMoves, activeDays, moveText, track, lawLine };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.RC = api;
})(this);
