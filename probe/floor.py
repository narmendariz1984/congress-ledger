import urllib.request, xml.etree.ElementTree as ET, sys
UA = "congress-ledger/1.0 (+https://github.com/narmendariz1984/congress-ledger)"
for wk in ("20261109", "20260914"):
    u = f"https://docs.house.gov/floor/Download.aspx?file=/billsthisweek/{wk}/{wk}.xml"
    try:
        b = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=60).read()
    except Exception as e:
        print("ERR", wk, e); continue
    print("==", wk, len(b), "bytes; head:", b[:300])
    r = ET.fromstring(b)
    print("root:", r.tag, r.attrib)
    for cat in r:
        print(" child:", cat.tag, cat.attrib)
        for it in cat.iter():
            if it.tag in ("floor-item",):
                print("   item attrs:", it.attrib)
                for ch in it: print("     ", ch.tag, ch.attrib, (ch.text or "").strip()[:120])
                break
        print("   items in this child:", sum(1 for x in cat.iter() if x.tag == "floor-item"))
        for it in [x for x in cat.iter() if x.tag == "floor-item"]:
            print("    -", (it.findtext("legis-num") or "").strip(), "|", (it.findtext("floor-text") or "").strip()[:90], "|", {k: v for k, v in it.attrib.items() if "date" in k})
