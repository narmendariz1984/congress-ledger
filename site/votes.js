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

  const api = { isDecisive, failed, split, majorities, crossovers, voteOf, billId, VOTE_WORD, notable, subject, headline, explain, decisions };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.RC = api;
})(this);
