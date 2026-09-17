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
- **`dismissed.txt`** -- same format as `applied.txt`, but permanent: the
  role is deleted from `seen_jobs.db` outright and never re-added, even if
  the board reposts the exact same URL later. Normally managed by the
  dashboard's **Delete** button (see below), not edited by hand.
- **`archived.txt`** -- same format again, but softer: the role stays in
  `seen_jobs.db`/`matches.md`, just moved into a collapsed "Archived"
  section instead of the main list. Normally managed by the dashboard's
  **Archive**/**Unarchive** buttons.
- **Secrets** (Settings -> Secrets and variables -> Actions), both optional
  -- without them, roles are still found but left unscored:
  - `ANTHROPIC_API_KEY` -- enables Jobscan-style scoring via Claude.
  - `RESUME_TEXT` -- your resume as plain text, pasted into the secret value.

## Dashboard actions (Archive / Delete)

The dashboard (`docs/index.html`) has per-row **Archive** and **Delete**
buttons that write straight to this repo via the GitHub REST API -- no
separate backend, since it's a static page. That needs a personal access
token with write access to this one repo:

1. Create a **fine-grained** token at
   [github.com/settings/personal-access-tokens/new](https://github.com/settings/personal-access-tokens/new).
2. Set **Repository access** to "Only select repositories" -> this repo.
3. Under **Permissions**, grant **Contents: Read and write** only.
4. Give it an expiration (90 days is reasonable) rather than "no expiration".
5. Paste it into the dashboard's "⚙ GitHub token" panel. It's saved only in
   that browser's `localStorage` -- it's never sent anywhere but
   `api.github.com`, and never reaches this repo, me, or any other viewer.

Clicking **Archive** appends the job's URL to `archived.txt`; **Delete**
appends it to `dismissed.txt` (after a confirmation, since it's permanent).
Either way, the commit lands immediately, but `seen_jobs.db`/`matches.md`
only catch up on the **next run** of `job_agent.py` (the daily schedule, or
a manual trigger from the Actions tab) -- the dashboard also updates its own
view instantly in that browser tab so it doesn't feel like nothing happened,
but that in-tab change doesn't survive a reload until the next real run
regenerates the page.

A token scoped this narrowly (one repo, contents only) is low-risk to keep
in a browser you control, but if you ever suspect it leaked, revoke it from
the same GitHub settings page.

## Files

- `job_agent.py` -- the agent itself.
- `discover_tokens.py` -- standalone helper (not run automatically) for
  finding a company's Greenhouse/Ashby/Lever token from its name/website.
- `company_status.csv` -- generated tracking sheet of every company checked
  and whether its token currently resolves.
- `matches.md` / `docs/index.html` -- generated output; committed back to
  the repo by the daily workflow.
