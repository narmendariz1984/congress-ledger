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
- [Voteview](https://voteview.com/data): Senate roll call list (CSV). senate.gov refuses automated clients, so the script doesn't fetch it; vote rows still link to the official senate.gov pages.
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

## Tests and checks

- `node --test tests/names.test.mjs` checks bill names, measure codes and state search against real cases (nominations, war powers and rule-overturning resolutions, cut-off Senate titles), plus every title in the current data.
- `python -m unittest discover -s tests` checks the keep rule, roll call discovery and House and Senate vote parsing, with no network calls.
- `node scripts/check.mjs` checks the data itself. It runs after every refresh: warnings go to the run summary, and serious problems (no House tallies, unreadable data, too few bills) fail the run so GitHub sends a notification.

The **Tests** workflow runs all three on every code change. Naming rules live in `site/names.js`, shared by the page, the tests and the check.
