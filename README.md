# Congress Bill Ledger

Tracks mature House and Senate bills: who wrote them, who cosponsored them, who blocked them, and what passed or died. Live at **congress.nikolasarmendariz.com**.

## How it updates

A GitHub Actions schedule (`.github/workflows/refresh.yml`) runs `scripts/fetch.py` every hour. The script reads the session calendar and only does work when it's useful:

| | Session days | Recess days |
|---|---|---|
| Floor votes | Hourly, 8am–11pm CT | Skipped |
| Bills | 6am, noon, 6pm, 11pm CT | 6am CT |

It writes `site/data/ledger.json` and commits only when the data changed. Cloudflare Pages redeploys the `site/` folder on each commit.

## Where data comes from

- [Congress.gov API](https://api.congress.gov/): bill details, actions, cosponsors, House roll calls (beta)
- [Senate roll call votes](https://www.senate.gov/legislative/votes_new.htm): vote list XML
- `data/curated.json`: hand-checked fields (blockers, attribution, footnotes). These always override fetched data.

Bills marked **AUTO** on the page were found by the script and haven't been reviewed yet.

## Add or correct a bill

Edit `data/curated.json`. A bill needs only its key, `congress`, `type` and `number`:

```json
"120-hr1234": { "congress": 120, "type": "hr", "number": 1234 }
```

Anything else you add (`status`, `blockers`, `fns`, ...) overrides what the script fetched.

## Secrets

The Congress.gov key lives only in **Settings → Secrets and variables → Actions** as `CONGRESS_API_KEY`. It is never written to a file or printed in logs. Don't commit keys; `.gitignore` blocks `.env` files.

## Run it yourself

```powershell
# normal (non-elevated) PowerShell, from the repo folder
$env:CONGRESS_API_KEY = Read-Host -MaskInput 'Congress API key'
$env:MODE = 'full'
python scripts/fetch.py
```

`MODE=offline` rebuilds from `data/curated.json` with no network or key.
