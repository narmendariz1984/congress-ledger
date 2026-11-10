"""One-off: does Congress.gov flag vehicle swaps? Prints titles, related bills and amendments.
Uses fetch.api (identifying User-Agent, key from the CONGRESS_API_KEY secret, never printed)."""
import json, os, random, re, sys, time
sys.path.insert(0, "scripts")
import fetch as F

KEY = os.environ.get("CONGRESS_API_KEY", "")
def safe(x):  # belt and braces: the responses shouldn't carry the key, but never print it
    s = json.dumps(x, ensure_ascii=False)
    return s.replace(KEY, "***") if KEY else s

ERRORS = []
def get(path, key, **p):
    time.sleep(0.4)  # low volume
    try:
        return F.api(path, **p).get(key) or []
    except Exception as e:  # noqa: BLE001
        ERRORS.append(f"/{path}: {e.__class__.__name__}")
        print("   error", f"/{path}: {e.__class__.__name__} {e}"[:200], flush=True)
        return []

def probe(c, t, n, deep=True):
    base = f"bill/{c}/{t}/{n}"
    out = {"bill": f"{c}-{t}{n}"}
    out["titles"] = [(x.get("titleType"), x.get("title")[:120], x.get("updateDate", "")[:10]) for x in get(base + "/titles", "titles", limit=100) if "error" not in x]
    out["related"] = [(f'{r.get("type")} {r.get("number")}', [(d.get("type"), d.get("identifiedBy")) for d in r.get("relationshipDetails") or []]) for r in get(base + "/relatedbills", "relatedBills", limit=100) if "error" not in r]
    if deep:
        out["amendments"] = [(f'{a.get("type")} {a.get("number")}', (a.get("purpose") or a.get("description") or "")[:140], (a.get("latestAction") or {}).get("text", "")[:100]) for a in get(base + "/amendments", "amendments", limit=50) if "error" not in a]
        acts = get(base + "/actions", "actions", limit=250)
        out["substitute_actions"] = [(a.get("actionDate"), a.get("text")[:160]) for a in acts if re.search(r"nature of a substitute|substitute amendment", a.get("text") or "", re.I)]
    return out

print("== the case: H.R. 2347 (vehicle) and S. 5653 (carried)")
for c, t, n in [(119, "hr", 2347), (119, "s", 5653)]:
    print(safe(probe(c, t, n)), flush=True)
print("== known shells from earlier Congresses")
for c, t, n in [(118, "hr", 815), (117, "hr", 2617)]:
    print(safe(probe(c, t, n)), flush=True)
print("== controls: 40 random 119th bills that passed one chamber (titles + related only)")
L = json.load(open("site/data/ledger.json"))
pool = [b for b in L["bills"] if b.get("status") == "passed1" and b.get("congress") == 119 and b["id"] != "119-hr2347"]
random.seed(7)
summary = {"n": 0, "procedural": 0, "new_title_types": {}}
for b in random.sample(pool, min(25, len(pool))):
    m = re.match(r"^(\d+)-([a-z]+)(\d+)$", b["id"])
    r = probe(int(m.group(1)), m.group(2), int(m.group(3)), deep=False)
    summary["n"] += 1
    proc = [x for x in r["related"] if any("procedur" in (d[0] or "").lower() for d in x[1])]
    if proc:
        summary["procedural"] += 1
    for tt, _, _ in r["titles"]:
        summary["new_title_types"][tt] = summary["new_title_types"].get(tt, 0) + 1
    print(safe({"bill": r["bill"], "procedural": proc, "title_types": sorted({x[0] for x in r["titles"]})}))
print("== summary", safe(summary), "errors:", len(ERRORS))
