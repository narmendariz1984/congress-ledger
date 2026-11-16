"""One-off: are GDELT news counts usable as "buzz" for bills? Prints counts and titles to eyeball."""
import json, time, urllib.parse, urllib.request
UA = "congress-ledger/1.0 (+https://github.com/narmendariz1984/congress-ledger)"
API = "https://api.gdeltproject.org/api/v2/doc/doc"
CASES = [("H.R. 2102", '"Major Richard Star Act"'), ("H.R. 9237", '"Take Care of America\'s Veterans Act"'),
         ("H.R. 9237 alt", '"veterans" "voice vote"'), ("H.R. 2347", '"American Affordability and Jobs Act"'),
         ("H.Res. 1655", 'Hegseth impeachment'), ("noise test", '"PROOF Act"'), ("H.R. 1013", '"Retirement Fairness for Charities"')]
for label, q in CASES:
    url = API + "?" + urllib.parse.urlencode({"query": f"{q} sourcecountry:US sourcelang:english", "mode": "artlist", "maxrecords": 75, "timespan": "7d", "format": "json", "sort": "datedesc"})
    try:
        body = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60).read()
        arts = (json.loads(body or b"{}") or {}).get("articles") or []
    except Exception as e:
        print(f"== {label}: ERROR {e.__class__.__name__}: {str(e)[:120]}"); time.sleep(7); continue
    doms = sorted({a.get("domain") for a in arts})
    print(f"== {label} [{q}]: {len(arts)} articles, {len(doms)} outlets: {', '.join(doms[:12])}")
    for a in arts[:6]:
        print(f"     {a.get('seendate','')[:8]} {a.get('domain','')[:24]:24} {a.get('title','')[:110]}")
    time.sleep(7)
