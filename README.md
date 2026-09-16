# jobagent3

Combined job-search agent: merges the location-accuracy/coverage engine from
`jobagent2` (geonamescache-based US-location filtering, Greenhouse/Ashby/
Lever/Workday/Workable coverage, hybrid-Chicago prioritization, posted-date
enrichment, stale-match pruning) with configurable keywords, Jobscan-style
resume scoring, applied-role suppression, and an HTML dashboard.

## How it works

`job_agent.py` polls each configured job board for roles matching your
keywords, filters out anything not actually reachable from Chicago/Illinois,
scores new matches against your resume (optional), and writes results to
`matches.md` and `docs/index.html` (a filterable dashboard, publishable via
GitHub Pages from the `docs/` folder).

Runs daily via `.github/workflows/daily.yml`, or manually with:

```
python job_agent.py
```

## Configuration

- **`keywords.txt`** -- one search keyword per line. Edit anytime on GitHub;
  the next run picks it up automatically. Controls both the title filter and
  the Workday/Workable search terms.
- **`applied.txt`** -- one entry per line: a full job URL hides just that
  role, a bare company name/token hides every role from that company. Edit
  right after you apply.
- **Secrets** (Settings -> Secrets and variables -> Actions), both optional
  -- without them, roles are still found but left unscored:
  - `ANTHROPIC_API_KEY` -- enables Jobscan-style scoring via Claude.
  - `RESUME_TEXT` -- your resume as plain text, pasted into the secret value.

## Files

- `job_agent.py` -- the agent itself.
- `discover_tokens.py` -- standalone helper (not run automatically) for
  finding a company's Greenhouse/Ashby/Lever token from its name/website.
- `company_status.csv` -- generated tracking sheet of every company checked
  and whether its token currently resolves.
- `matches.md` / `docs/index.html` -- generated output; committed back to
  the repo by the daily workflow.
