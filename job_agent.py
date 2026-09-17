#!/usr/bin/env python3
"""
Job Search Agent (combined edition)
------------------------------------
Polls Greenhouse, Ashby, Lever, Workday, and Workable job boards for a
curated list of companies, plus a cross-customer Workable search.

Greenhouse: uses the ?live=true parameter so only active, published,
accepting-applications roles are returned.

Ashby: uses the public posting-api, which only returns currently published
job postings, and includes an explicit isRemote flag.

Filters for implementation-type roles (keywords come from keywords.txt when
present, otherwise the built-in TITLE_KEYWORDS default), rejects roles that
aren't actually reachable from Chicago/Illinois (see location_matches()),
scores each new match against your resume using the Claude API in a
Jobscan-style breakdown (optional -- needs ANTHROPIC_API_KEY + RESUME_TEXT),
dedupes against previously seen roles, hides anything you've already applied
to (applied.txt), and writes results to matches.md and a filterable HTML
dashboard (docs/index.html) in the repo.

No email required. Check matches.md (or the dashboard) after each run.
"""

import os
import re
import csv
import json
import html
import time
import sqlite3
import threading
import unicodedata
import urllib.request
import urllib.error
import urllib.parse
import concurrent.futures
from datetime import datetime, timezone

import geonamescache

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

GREENHOUSE_COMPANIES = [
    # --- CONFIRMED working ---
    "fourkites", "thanx", "benchprep", "alphasense", "degreed",
    "greenhouse", "submittable", "samsara", "brightflag",

    # --- Chicago / Midwest SaaS ---
    "sproutsocial", "mantl", "loop", "logicgate", "maintainx", "bswift",
    "showpad", "g2", "shipbob", "project44", "amount", "relativity", "vibes",

    # --- HR / payroll / benefits SaaS ---
    "gusto", "rippling", "justworks", "betterup", "guideline", "lattice",
    "cultureamp", "15five", "bamboohr", "deel", "remote", "velocityglobal",
    "papayaglobal", "hibob",

    # --- Fintech / payments SaaS ---
    "ramp", "brex", "mercury", "moderntreasury", "plaid", "marqeta", "unit",
    "lithic", "highnote", "tipalti", "billdotcom", "melio", "stripe",

    # --- Data / analytics / martech SaaS ---
    "hightouch", "amplitude", "mixpanel", "fivetran", "dbtlabs", "hex",
    "census", "iterable", "braze", "klaviyo", "segment", "rudderstack",
    "snowflake", "databricks", "starburst", "sigmacomputing", "thoughtspot",

    # --- Customer experience / success / comms SaaS ---
    "gainsight", "totango", "front", "intercom", "zendesk", "dialpad",
    "talkdesk", "gong", "kustomer", "ada", "forethought",

    # --- Security / compliance / GRC ---
    "drata", "vanta", "secureframe", "onetrust", "snyk", "1password",
    "abnormalsecurity", "huntress", "semgrep",

    # --- Vertical / ops SaaS (heavy implementation needs) ---
    "servicetitan", "procore", "toasttab", "olo", "flexport", "settle",
    "tractian", "fountain", "workstream",

    # --- Dev tools / infra SaaS ---
    "gitlab", "hashicorp", "datadog", "pagerduty", "launchdarkly",
    "circleci", "harness", "sentry", "postman", "retool", "vercel", "netlify",

    # --- Productivity / collaboration SaaS ---
    "airtable", "notion", "figma", "lucidsoftware", "smartsheet", "asana",
    "monday", "clickup", "miro", "loom", "calendly", "docusign", "boxhq",
    "dropbox", "grammarly", "webflow", "zapier", "coda",

    # --- AI / emerging SaaS (AI angle fits your background) ---
    "writer", "glean", "sierra", "cresta", "moveworks", "abridge", "harvey",
    "hebbia", "scale", "instabase",

    # --- Marketing / sales SaaS ---
    "hubspot", "outreach", "salesloft", "apollo", "clari", "6sense",
    "demandbase", "zoominfo", "seismic", "highspot",

    # --- E-commerce / retail SaaS ---
    "shopify", "bigcommerce", "narvar", "yotpo", "attentivemobile", "bolt",
    "fabric", "rithum",

    # --- Education / learning SaaS ---
    "coursera", "udemy", "guild", "instructure", "360learning",

    # --- Insurance / legal / proptech SaaS ---
    "ethos", "newfront", "clio", "ironclad", "evisort", "qualia", "vts",

    # --- Auto-discovered and verified by discover_tokens.py ---
    "attentive", "billcom", "boxinc", "carta", "checkr", "cloudflare", "coinbase", "dbtlabsinc", "harnessinc", "papaya", "robinhood", "scaleai", "shipbobinc", "toast",

    # --- From LinkedIn network export -- best-guess tokens, UNVERIFIED.
    # A wrong guess here just 404s on the first run ("board not found") and
    # gets skipped -- prune those lines once you see them.
    "contentsquare", "quantummetric", "newrelic", "pendo", "anthropic",
    "spoton", "semrush", "scylladb", "rapidsos", "tripleseat", "instrumentl",
    "optibus", "zerohash", "confluent", "grindr", "revenuewell", "datastax",
    "authenticx", "compound", "kin", "tealium", "yello", "redfin",
    "coreweave", "typeface", "doppel", "origamirisk", "liveramp", "imgix",
    "dust", "jiko", "specright", "dreamdata", "firstdue", "vantaca",
    "aclaimant", "allegrow", "amperity", "apiture", "avature", "basis",
    "beyondfinance", "boomi", "censys", "cision", "comply", "conversica",
    "conviva", "coupa", "cyncly", "dealhub", "franconnect", "genesys",
    "icapital", "knotch", "logiwa", "momentive", "nearmap", "ncino",
    "nuvei", "opploans", "qualtrics", "questsoftware", "safetyculture",
    "sitecore", "smartlinx", "softchoice", "usertesting", "voltus",
    "waitwhile", "wunderkind", "yext", "zywave", "rula", "papa",
    "pieinsurance", "sdocs", "qbench",

    # --- From Contentsquare integrations-partner catalog -- best-guess
    # tokens, UNVERIFIED. Same caveat as the blocks above.
    "abtasty", "algolia", "bazaarvoice", "bloomreach", "bluetriangle",
    "blueconic", "brightcove", "cloudinary", "comscore", "convert",
    "coveo", "drift", "dynatrace", "emplifi", "freshworks", "heap",
    "hotjar", "inmoment", "intellimize", "invoca", "medallia", "monetate",
    "ninetailed", "optimizely", "powerreviews", "sitespect", "verint",
    "vimeo", "vwo", "yieldify",

    # --- Confirmed via web search: these two run on Greenhouse's newer
    # job-boards.greenhouse.io frontend, not the custom/Workday ATS they
    # were originally assumed to use.
    "adyen", "twilio",
]

# Ashby company tokens (the slug in jobs.ashbyhq.com/<token>).
ASHBY_COMPANIES = [
    # --- CONFIRMED (from our own sessions) ---
    "benepass", "drata", "spare", "clasp-group", "uniti", "avoca",
    "savvymoney", "opengov",

    # --- CONFIRMED (named directly by Ashby as customers) ---
    "ramp", "notion", "vanta", "posthog", "marqeta", "hackerone",
    "junipersquare", "away", "formenergy", "fullstory", "multiverse",
    "montecarlodata", "flockfreight", "sequoia",

    # --- AI / emerging tech (heavy Ashby adoption in this segment) ---
    "linear", "cursor", "perplexity-ai", "character-ai", "watershed",
    "together-ai", "worldlabs", "runwayml", "assemblyai", "modal",
    "baseten", "fireworks-ai", "cohere", "adept", "imbue",

    # --- Fintech / payments (Series A-C, Ashby's core segment) ---
    "mercury", "rho", "middesk", "sardine", "highbeam", "column",
    "increase", "bridge", "parafin", "settle-inc",

    # --- HR / people ops / benefits SaaS ---
    "zip", "assort-health", "included-health", "modernhealth", "forma",
    "sequoia-consulting", "trinet",

    # --- Dev tools / infra (Ashby's other core segment) ---
    "temporal", "warp", "railway", "fly-io", "neon", "turso", "supabase",
    "convex", "trigger-dev", "resend",

    # --- Data / analytics ---
    "hex-technologies", "census", "hightouch", "mode", "count",

    # --- Customer / sales / support SaaS ---
    "attio", "clay-run", "koala", "vessel", "common-room", "endgame",

    # --- Security / compliance ---
    "secureframe", "nudge-security", "cyera",

    # --- Vertical SaaS / other notable Ashby customers ---
    "whoop", "clipboard-health", "arc", "mercor", "crusoe-energy",
    "flexport", "solugen",

    # --- Auto-discovered and verified by discover_tokens.py ---
    "1password", "abridge", "betterup", "clickup", "deel", "demandbase", "frontcareers", "g2", "gainsight", "harvey", "hebbia-ai", "hex", "instructure", "ironcladhq", "kustomer", "loom", "maintainx", "miro", "moderntreasury", "newfront", "plaid", "semgrep", "sentry", "sierra", "snowflake", "snyk", "talkdesk", "unit", "writer", "xero", "zapier",

    # --- From LinkedIn network -- best-guess tokens, UNVERIFIED.
    "pushsecurity", "seasoned",
]

# Lever company tokens (the slug in jobs.lever.co/<token>).
LEVER_COMPANIES = [
    # --- CONFIRMED (named as Lever customers by multiple sources) ---
    "shopify", "netflix", "spotify", "atlassian", "klarna", "palantir",
    "xero", "1password", "remote", "rackspace", "gettyimages", "nielsen",

    # --- Other well-known Lever-using SaaS / tech companies ---
    "eventbrite", "yelp", "quora", "reddit", "opendoor", "lyft",
    "netsuite", "checkr", "gusto", "zapier", "carta", "brightside",
    "greenhouse", "kickstarter", "buzzfeed", "patreon", "gopuff",
    "impossiblefoods", "peloton", "digitalocean", "sofi", "affirm",
    "chime", "toast", "instacart", "doordash", "flexport", "faire",
    "gopro", "cloudflare", "twitch", "medium", "wework", "compass",
    "betterment", "wealthfront", "robinhood", "coinbase", "gemini",
    "kraken", "opensea", "chainalysis", "circle", "anchorage",

    # --- Professional services / implementation-heavy verticals ---
    "clio", "procore", "smartrecruiters", "greenhouse-software",
    "seismic", "highspot", "gong", "outreach", "salesloft",

    # --- Auto-discovered and verified by discover_tokens.py ---
    "15five", "360learning", "clari", "olo", "tractian", "velocityglobal",
]

# Workday: each tenant needs its subdomain number (wd1-wd5+) and the site
# slug the company chose, neither of which is guessable from the company
# name alone -- each entry here was verified against the company's real
# public careers URL.
WORKDAY_COMPANIES = {
    "tmobile": {"wd": "wd1", "site": "External"},
    "target": {"wd": "wd5", "site": "targetcareers"},
    "accenture": {"wd": "wd103", "site": "AccentureCareers"},
    "acehardware": {"wd": "wd1", "site": "External"},
    "cvshealth": {"wd": "wd1", "site": "CVS_Health_Careers"},  # covers Aetna
    "alight": {"wd": "wd5", "site": "Careers"},
    "allstate": {"wd": "wd5", "site": "allstate_careers"},
    "att": {"wd": "wd1", "site": "ATTGeneral"},
    "bah": {"wd": "wd1", "site": "BAH_Jobs"},  # Booz Allen Hamilton
    "bridgestone": {"wd": "wd5", "site": "External"},
    "cdk": {"wd": "wd1", "site": "CDK"},
    "cengage": {"wd": "wd5", "site": "CengageNorthAmericaCareers"},
    "cmegroup": {"wd": "wd1", "site": "cme_careers"},
    "generalmotors": {"wd": "wd5", "site": "Careers_GM"},
    "hp": {"wd": "wd5", "site": "ExternalCareerSite"},
    "icf": {"wd": "wd5", "site": "ICFExternal_Career_Site"},
    "jj": {"wd": "wd5", "site": "JJ"},  # Johnson & Johnson
    "kyndryl": {"wd": "wd5", "site": "KyndrylProfessionalCareers"},
    "morningstar": {"wd": "wd5", "site": "Americas"},
    "nordstrom": {"wd": "wd501", "site": "nordstrom_careers"},
    "northwesternmutual": {"wd": "wd5", "site": "CORPORATE-CAREERS"},
    "pnc": {"wd": "wd5", "site": "External"},
    "globalhr": {"wd": "wd5", "site": "REC_RTX_Ext_Gateway"},  # Raytheon/RTX
    "roberthalf": {"wd": "wd1", "site": "RobertHalfStaffingCareers"},
    "rockwellautomation": {"wd": "wd1", "site": "External_Rockwell_Automation"},
    "salesforce": {"wd": "wd12", "site": "External_Career_Site"},
    "uaa": {"wd": "wd12", "site": "EXT"},  # United Airlines
    "wf": {"wd": "wd1", "site": "WellsFargoJobs"},  # Wells Fargo
    "williams": {"wd": "wd5", "site": "External"},  # William Blair
}

# Default search keywords -- overridden by keywords.txt when present (see
# below), so you can edit the search terms on GitHub without touching code.
TITLE_KEYWORDS = [
    "implementation manager",
    "implementation consultant",
    "implementation specialist",
    "onboarding manager",
    "onboarding specialist",
    "technical project manager",
    "professional services",
]

KEYWORDS_FILE = os.environ.get("KEYWORDS_FILE", "keywords.txt")
if os.path.exists(KEYWORDS_FILE):
    with open(KEYWORDS_FILE, encoding="utf-8") as _kf:
        _custom_keywords = [
            ln.strip().lower() for ln in _kf
            if ln.strip() and not ln.strip().startswith("#")
        ]
    if _custom_keywords:
        TITLE_KEYWORDS = _custom_keywords

# Workable cross-customer search queries. None means "use TITLE_KEYWORDS",
# so editing keywords.txt controls Workable search terms too, without a
# separate list to keep in sync.
WORKABLE_SEARCH_QUERIES = None
WORKABLE_MAX_PAGES_PER_QUERY = 5  # 20 jobs/page -> up to 100 jobs per query

US_EXPLICIT_MARKERS = ["united states", "usa", "u.s.a", "u.s."]

# Full US state names (Illinois/Chicago are handled separately -- they
# always pass regardless of remote status). Used to detect a "remote" role
# that's actually pinned to one specific *other* state, which is a false
# positive for a Chicago/Illinois-based search.
US_STATE_NAMES = [
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine",
    "maryland", "massachusetts", "michigan", "minnesota", "mississippi",
    "missouri", "montana", "nebraska", "nevada", "new hampshire",
    "new jersey", "new mexico", "new york", "north carolina",
    "north dakota", "ohio", "oklahoma", "oregon", "pennsylvania",
    "rhode island", "south carolina", "south dakota", "tennessee",
    "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming", "district of columbia",
]

US_STATE_ABBREVS = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id",
    "il", "in", "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms",
    "mo", "mt", "ne", "nv", "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok",
    "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv",
    "wi", "wy", "dc",
}

# Region acronyms that indicate non-US remote scope but aren't real place
# names in any geographic database (so geonamescache below can't catch them).
REGION_MARKERS = ["emea", "apac", "latam", "asia pacific"]

# Well-known, unambiguous (not-an-ordinary-English-word) foreign cities that
# are safe to scan broadly across location+title+url. This matters because
# some boards (Workable in particular) embed the real city only in the URL
# slug, e.g. ".../technical-project-manager-in-kuala-lumpur-at-innovatrics",
# never in the structured location field -- and the geonamescache lookup
# below is deliberately NOT run against title/url text (a real city
# database has ~35,000 entries, and plenty of them collide with ordinary
# English words like "Officer", "Human", "Time", or the payroll system
# "ADP" -- fine to risk in a short, structured location field, not safe to
# risk against free-text job titles).
SAFE_BROAD_CITIES = [
    "toronto", "montreal", "munich", "hamburg", "madrid", "barcelona",
    "amsterdam", "rotterdam", "krakow", "lisbon", "prague", "bucharest",
    "bangalore", "bengaluru", "mumbai", "delhi", "hyderabad", "pune",
    "chennai", "manila", "metro manila", "sydney", "brisbane", "auckland",
    "wellington", "tokyo", "osaka", "seoul", "tel aviv", "sao paulo",
    "rio de janeiro", "mexico city", "bogota", "buenos aires", "santiago",
    "dubai", "abu dhabi", "cape town", "johannesburg", "lagos",
    "nairobi", "shanghai", "beijing", "shenzhen", "taipei",
    "ho chi minh", "hanoi", "bangkok", "jakarta", "kuala lumpur",
    "kyiv", "kiev", "zurich", "geneva", "vienna", "brussels", "stockholm",
    "oslo", "copenhagen", "helsinki", "budapest", "guadalajara", "lahore",
]

# ---------------------------------------------------------------------------
# Geographic lookup (geonamescache) -- replaces a hand-maintained city
# blocklist, which can never keep up: the world has thousands of cities, and
# every one we haven't personally thought to add slips straight through.
# Built once at import time; ~35,000 cities plus every country, each mapped
# to the largest population seen for that name in each country, so an
# ambiguous name (Birmingham UK vs. AL, St. Louis vs. the small French town)
# is resolved by which one is actually the well-known place, not by picking
# one arbitrarily.
# ---------------------------------------------------------------------------

def _strip_accents(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


# Names excluded from the geographic lookup entirely: our own US state names
# (geonamescache lists "Georgia" as a country and "Virginia"/"Indiana" as
# obscure foreign towns -- letting those through would silently reintroduce
# exactly the false-rejection bug this replaces), plus common English words
# and names that happen to coincidentally match obscure places worldwide
# (confirmed by testing against realistic job-posting vocabulary).
_GEO_EXCLUDE = {_strip_accents(s).lower() for s in US_STATE_NAMES} | {
    "chicago", "illinois", "remote", "us", "usa", "united states",
    "man", "the", "all", "one", "she", "and", "was", "for", "are", "but",
    "not", "you", "care", "human", "officer", "part", "time", "adp", "ben",
    "eve", "leo", "max", "sam", "tom", "chad", "jordan", "ray", "dan",
    "ana", "mia", "ada", "central", "north", "south", "east", "west",
    "enterprise",
}


def _build_geo_lookup():
    gc = geonamescache.GeonamesCache()
    place_pop = {}  # normalized name -> {country_code: max population}

    def add(name, cc, pop):
        key = _strip_accents(name).lower().strip()
        if len(key) < 4 or key in _GEO_EXCLUDE:
            return
        d = place_pop.setdefault(key, {})
        d[cc] = max(d.get(cc, 0), pop or 0)

    for c in gc.get_cities().values():
        add(c["name"], c["countrycode"], c.get("population", 0))
        for alt in c.get("alternatenames", []):
            add(alt, c["countrycode"], c.get("population", 0))

    country_names = {}
    for code, c in gc.get_countries().items():
        key = _strip_accents(c["name"]).lower().strip()
        if len(key) >= 4 and key not in _GEO_EXCLUDE:
            country_names[key] = code

    return place_pop, country_names


PLACE_POPULATIONS, COUNTRY_NAMES = _build_geo_lookup()
_MAX_PLACE_WORDS = 4


def find_place_signal(text):
    """Scan already-normalized (lowercase, accent-stripped) text for country
    and city names. Returns "foreign" (a non-US country, or a city whose
    largest non-US population outweighs its US one), "us" (a city that IS
    the well-known US place), or None if nothing recognized. Greedily
    matches the longest phrase at each position so e.g. "san francisco"
    isn't re-split into "san" + "francisco" (the latter alone is a small
    Cuban town with no US entry at all)."""
    words = re.findall(r"[a-z0-9]+", text)
    n = len(words)
    verdict = None
    i = 0
    while i < n:
        matched_len = 0
        for length in range(min(_MAX_PLACE_WORDS, n - i), 0, -1):
            phrase = " ".join(words[i:i + length])
            if phrase in COUNTRY_NAMES:
                if COUNTRY_NAMES[phrase] != "US":
                    return "foreign"
                verdict = verdict or "us"
                matched_len = length
                break
            if phrase in PLACE_POPULATIONS:
                pops = PLACE_POPULATIONS[phrase]
                us_pop = pops.get("US", 0)
                max_other = max((p for cc, p in pops.items() if cc != "US"), default=0)
                if "US" in pops and us_pop > max_other:
                    verdict = verdict or "us"
                elif max_other > 0:
                    return "foreign"
                matched_len = length
                break
        i += matched_len if matched_len else 1
    return verdict

RESUME_TEXT = os.environ.get("RESUME_TEXT", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-5"

# Caps how many score_role() calls (i.e. real Claude API calls) a single run
# will make -- unset/blank means unlimited (the normal daily-run behavior).
# Set to a small number (or 0) when manually testing, e.g. to confirm the
# rest of the pipeline (fetch/filter/dashboard/commit-and-push) works
# without paying to score dozens of matches every test run. Jobs beyond the
# cap still get added to matches.md, just unscored, exactly like running
# with no ANTHROPIC_API_KEY at all.
_max_score_calls_raw = os.environ.get("MAX_SCORE_CALLS", "").strip()
MAX_SCORE_CALLS = int(_max_score_calls_raw) if _max_score_calls_raw.isdigit() else None

# When set, skip the full company/board scan entirely and only rescore
# already-recorded matches that never got a real score (e.g. because
# MAX_SCORE_CALLS capped a prior run, or scoring wasn't configured yet).
# See rescore_pending().
RESCORE_ONLY = os.environ.get("RESCORE_ONLY", "").strip().lower() in ("1", "true", "yes")

DB_PATH = os.environ.get("DB_PATH", "seen_jobs.db")
MATCHES_FILE = os.environ.get("MATCHES_FILE", "matches.md")
COMPANY_STATUS_FILE = os.environ.get("COMPANY_STATUS_FILE", "company_status.csv")
APPLIED_FILE = os.environ.get("APPLIED_FILE", "applied.txt")
DISMISSED_FILE = os.environ.get("DISMISSED_FILE", "dismissed.txt")
ARCHIVED_FILE = os.environ.get("ARCHIVED_FILE", "archived.txt")
DASHBOARD_FILE = os.environ.get("DASHBOARD_FILE", os.path.join("docs", "index.html"))

# GitHub Actions sets these automatically during a workflow run -- used only
# to tell the dashboard's "Archive"/"Delete" buttons which repo/branch to
# write dismissed.txt/archived.txt entries to via the GitHub API. Falls back
# to this repo's own coordinates when run outside Actions (e.g. locally).
GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "tomhcooke/jobagent3")
GITHUB_BRANCH = os.environ.get("GITHUB_REF_NAME", "main")

COMPANY_STATUS_FIELDS = [
    "company", "token", "platform", "in_network", "source",
    "access_status", "jobs_found_last_run", "last_checked", "notes",
]


# ---------------------------------------------------------------------------
# COMPANY STATUS -- a human-viewable sheet of every company we know about:
# whether we have a working token for their job board, which platform
# (greenhouse/ashby/lever), whether they're in your network, and why a
# company was left out if it wasn't added at all. Every real run updates
# access_status/jobs_found_last_run/last_checked for companies we actually
# queried; manually-edited columns (in_network, source, notes, company) are
# preserved across runs.
# ---------------------------------------------------------------------------

def _company_status_key(row):
    """(platform, token) uniquely identifies an actively-tracked company, but
    "not_added" rows have no platform/token at all -- keying purely on those
    would collapse every one of them onto the same ("", "") entry. Fall back
    to the company name for those."""
    platform, token = row.get("platform", ""), row.get("token", "")
    if token:
        return (platform, token)
    return ("", row.get("company", ""))


def load_company_status():
    rows = {}
    if not os.path.exists(COMPANY_STATUS_FILE):
        return rows
    with open(COMPANY_STATUS_FILE, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows[_company_status_key(row)] = row
    return rows


def save_company_status(rows):
    ordered = sorted(rows.values(), key=lambda r: (r.get("platform", ""), r.get("company", "").lower()))
    with open(COMPANY_STATUS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COMPANY_STATUS_FIELDS)
        writer.writeheader()
        for row in ordered:
            writer.writerow({field: row.get(field, "") for field in COMPANY_STATUS_FIELDS})


def record_company_status(rows, platform, token, status, jobs_found):
    """Update (or insert) the row for a company we just actually queried.
    status is "ok"/"not_found"/"error" from the fetch_* functions."""
    key = (platform, token)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row = rows.get(key, {
        "company": token, "token": token, "platform": platform,
        "in_network": "unknown", "source": "", "notes": "",
    })
    access_status = {"ok": "confirmed", "not_found": "not_found", "error": "error"}[status]
    # A connection error doesn't disprove a previously-confirmed token --
    # only overwrite a prior "confirmed"/"not_found" verdict with real news.
    if status == "error" and row.get("access_status") in ("confirmed", "not_found"):
        row["last_checked"] = row.get("last_checked", today)
    else:
        row["access_status"] = access_status
        row["jobs_found_last_run"] = jobs_found if status == "ok" else 0
        row["last_checked"] = today
    rows[key] = row


# ---------------------------------------------------------------------------
# APPLIED / DISMISSED / ARCHIVED -- three flat text-file lists, all in the
# same format: one entry per line, a full job URL matches just that role, a
# bare company name/token matches every role from that company. All three
# can also be edited by hand on GitHub, same as keywords.txt.
#
#   applied.txt   -- you applied. Hidden from matches.md/dashboard.
#   dismissed.txt -- not interested, ever. Hidden AND the row is deleted
#                    from seen_jobs.db, and process_jobs() refuses to
#                    re-add it even if the board reposts the same URL.
#                    (This is the "Delete" dashboard button.)
#   archived.txt  -- out of the main list, but still on record. The row
#                    stays in seen_jobs.db with an `archived` flag, and
#                    matches.md/the dashboard render it in a separate
#                    section instead of dropping it. (The "Archive" button.)
# ---------------------------------------------------------------------------

def _load_entry_list(path):
    entries = set()
    if not os.path.exists(path):
        return entries
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                entries.add(line.lower())
    return entries


def load_applied():
    return _load_entry_list(APPLIED_FILE)


def load_dismissed():
    return _load_entry_list(DISMISSED_FILE)


def load_archived():
    return _load_entry_list(ARCHIVED_FILE)


def _matches_entry_list(match, entries):
    if not entries:
        return False
    url = (match.get("url") or "").lower()
    company = (match.get("company") or "").lower()
    return url in entries or company in entries


def is_applied(match, applied_entries):
    return _matches_entry_list(match, applied_entries)


def is_dismissed(match, dismissed_entries):
    return _matches_entry_list(match, dismissed_entries)


# ---------------------------------------------------------------------------
# DATABASE
# ---------------------------------------------------------------------------

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen (
            job_id TEXT PRIMARY KEY,
            source TEXT,
            company TEXT,
            title TEXT,
            url TEXT,
            location TEXT,
            score INTEGER,
            first_seen TEXT,
            status TEXT DEFAULT 'open',
            closed_date TEXT
        )
    """)
    # Migration: add any columns missing from older versions of this table
    # instead of failing. Existing rows get sensible defaults.
    existing_cols = [row[1] for row in conn.execute("PRAGMA table_info(seen)")]
    if "source" not in existing_cols:
        conn.execute("ALTER TABLE seen ADD COLUMN source TEXT DEFAULT 'greenhouse'")
        print("  (migrated seen_jobs.db to add 'source' column)")
    if "location" not in existing_cols:
        conn.execute("ALTER TABLE seen ADD COLUMN location TEXT DEFAULT ''")
        print("  (migrated seen_jobs.db to add 'location' column)")
    if "status" not in existing_cols:
        conn.execute("ALTER TABLE seen ADD COLUMN status TEXT DEFAULT 'open'")
        print("  (migrated seen_jobs.db to add 'status' column)")
    if "closed_date" not in existing_cols:
        conn.execute("ALTER TABLE seen ADD COLUMN closed_date TEXT")
        print("  (migrated seen_jobs.db to add 'closed_date' column)")
    if "posted_date" not in existing_cols:
        conn.execute("ALTER TABLE seen ADD COLUMN posted_date TEXT DEFAULT ''")
        print("  (migrated seen_jobs.db to add 'posted_date' column)")
    if "matched_keyword" not in existing_cols:
        conn.execute("ALTER TABLE seen ADD COLUMN matched_keyword TEXT DEFAULT ''")
        print("  (migrated seen_jobs.db to add 'matched_keyword' column)")
    if "score_detail" not in existing_cols:
        conn.execute("ALTER TABLE seen ADD COLUMN score_detail TEXT DEFAULT ''")
        print("  (migrated seen_jobs.db to add 'score_detail' column)")
    if "archived" not in existing_cols:
        conn.execute("ALTER TABLE seen ADD COLUMN archived INTEGER DEFAULT 0")
        print("  (migrated seen_jobs.db to add 'archived' column)")
    conn.commit()
    return conn


def already_seen(conn, job_id):
    cur = conn.execute("SELECT 1 FROM seen WHERE job_id = ?", (str(job_id),))
    return cur.fetchone() is not None


def mark_seen(conn, job_id, source, company, title, url, location, score,
              posted_date="", matched_keyword="", score_detail=""):
    # Defensive coercion: a field arriving as something other than a plain
    # string (e.g. a nested dict from an API whose shape wasn't fully
    # documented) should never crash the whole run -- just stringify it.
    def _safe_str(v):
        if isinstance(v, dict):
            return str(v.get("name") or v.get("title") or v.get("id") or v)
        return str(v) if v is not None else ""

    company = _safe_str(company)
    title = _safe_str(title)
    url = _safe_str(url)
    location = _safe_str(location)
    posted_date = _safe_str(posted_date)
    matched_keyword = _safe_str(matched_keyword)
    score_detail = _safe_str(score_detail)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn.execute(
        """INSERT OR IGNORE INTO seen
           (job_id, source, company, title, url, location, score, first_seen,
            posted_date, matched_keyword, score_detail)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (str(job_id), source, company, title, url, location, score, today,
         posted_date, matched_keyword, score_detail)
    )
    conn.commit()


def prune_stale_matches(conn):
    """
    Re-validate every previously-recorded job against the CURRENT
    title_matches()/location_matches() logic and delete any that no longer
    pass. A row is only ever inserted once (already_seen() skips it forever
    after that), so without this, a bug fix to the filters -- like catching
    a non-US location it used to miss, or a keywords.txt edit -- would never
    clean up the old bad rows already sitting in matches.md. Safe to delete
    outright: if the job is still genuinely live and would (correctly) still
    fail the filter, it simply won't be re-added; if the filter was wrong and
    it's actually fine, the next real fetch will see it's not already_seen
    and re-add it fresh.
    """
    rows = conn.execute("SELECT job_id, title, location, url FROM seen").fetchall()
    stale_ids = [
        job_id for job_id, title, location, url in rows
        if not title_matches(title) or not location_matches(location, title, url)
    ]
    if stale_ids:
        conn.executemany("DELETE FROM seen WHERE job_id = ?", [(jid,) for jid in stale_ids])
        conn.commit()
        print(f"Pruned {len(stale_ids)} stale match(es) that no longer pass the current filters.")


def remove_dismissed(conn, dismissed_entries):
    """Delete any row already sitting in seen_jobs.db that matches
    dismissed.txt -- covers a job dismissed via the dashboard's Delete
    button after it was already recorded on a prior run. process_jobs()
    separately refuses to re-insert a dismissed job going forward."""
    if not dismissed_entries:
        return
    rows = conn.execute("SELECT job_id, url, company FROM seen").fetchall()
    dismissed_ids = [
        job_id for job_id, url, company in rows
        if _matches_entry_list({"url": url, "company": company}, dismissed_entries)
    ]
    if dismissed_ids:
        conn.executemany("DELETE FROM seen WHERE job_id = ?", [(jid,) for jid in dismissed_ids])
        conn.commit()
        print(f"Removed {len(dismissed_ids)} dismissed match(es) per {DISMISSED_FILE}.")


def apply_archived_flags(conn, archived_entries):
    """Flip the `archived` column on for any row matching archived.txt, and
    back off for anything that's since been removed from that file (e.g. you
    changed your mind and deleted the line by hand)."""
    rows = conn.execute("SELECT job_id, url, company, archived FROM seen").fetchall()
    changed = 0
    for job_id, url, company, archived in rows:
        should_be = 1 if _matches_entry_list({"url": url, "company": company}, archived_entries) else 0
        if (archived or 0) != should_be:
            conn.execute("UPDATE seen SET archived = ? WHERE job_id = ?", (should_be, job_id))
            changed += 1
    if changed:
        conn.commit()
        print(f"Updated archived flag on {changed} match(es) per {ARCHIVED_FILE}.")


def get_all_matches(conn):
    """Return every role ever logged, most recently found first."""
    rows = conn.execute(
        """SELECT source, company, title, url, location, score, first_seen, status,
                  closed_date, posted_date, matched_keyword, score_detail, archived
           FROM seen ORDER BY first_seen DESC, company ASC"""
    ).fetchall()
    results = []
    for (source, company, title, url, location, score, first_seen, status,
         closed_date, posted_date, matched_keyword, score_detail, archived) in rows:
        results.append({
            "source": source, "company": company, "title": title, "url": url,
            "location": location, "score": score, "first_seen": first_seen,
            "status": status or "open", "closed_date": closed_date,
            "posted_date": posted_date or "",
            "matched_keyword": matched_keyword or "",
            "score_detail": score_detail or "",
            "archived": bool(archived),
        })
    return results


def update_closed_status(conn, live_ids_by_company):
    """
    For every (source, company) we successfully checked this run, compare the
    historical roles on file against the current live job list. Anything no
    longer present gets marked closed with today's date. Anything that
    reappears (a role reopening) flips back to open. Companies we could NOT
    verify this run (network error, or pruned out of the config) are left
    untouched -- silence is not evidence of closure.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    checked_companies = set(live_ids_by_company.keys())

    rows = conn.execute("SELECT job_id, source, company, status FROM seen").fetchall()
    for job_id, source, company, status in rows:
        key = (source, company)
        if key not in checked_companies:
            continue  # couldn't verify this company this run -- leave as-is

        live_ids = live_ids_by_company[key]
        if job_id in live_ids:
            if status != "open":
                conn.execute("UPDATE seen SET status = 'open', closed_date = NULL WHERE job_id = ?", (job_id,))
        else:
            if status != "closed":
                conn.execute("UPDATE seen SET status = 'closed', closed_date = ? WHERE job_id = ?", (today, job_id))
    conn.commit()


def _parse_date_to_str(value, is_epoch_ms=False):
    """Best-effort: turn an ISO8601 string or epoch-ms value into
    'YYYY-MM-DD'. Returns '' if it can't be parsed -- never raises, since a
    board's exact field format can change without notice."""
    if not value:
        return ""
    try:
        if is_epoch_ms:
            dt = datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError, OverflowError, OSError):
        return ""


# ---------------------------------------------------------------------------
# CONCURRENCY -- fetch_* calls run in a small per-source thread pool (see
# main()) instead of one at a time, since these are pure I/O waits. Each
# shared host gets its own RateLimiter enforcing a minimum spacing between
# actual request dispatches, independent of how many threads are running,
# so throughput is bounded by a safe per-host rate rather than by thread
# count -- concurrency just lets response latency overlap across threads.
# Caps are set from each board's documented/informally-known tolerance:
#   - Greenhouse: no published limit for reads, but "hammering in tight
#     loops gets blocked" -- kept moderate (~6-7/sec ceiling).
#   - Ashby: informal ~100 requests/minute, with 500-600ms spacing
#     recommended between requests.
#   - Lever: general Data API allows 10/sec sustained; kept a bit more
#     conservative since our specific read endpoint isn't documented.
#   - Workday: no shared limiter needed -- each tenant is its own separate
#     host (e.g. target.wd5.myworkdayjobs.com vs tmobile.wd1...), so
#     concurrency across tenants carries no shared-host risk. Pacing is
#     applied per-tenant instead, directly in fetch_workday_jobs() below.
# ---------------------------------------------------------------------------

class RateLimiter:
    """Thread-safe minimum-interval limiter: wait() blocks only as long as
    needed so no two calls across any thread dispatch less than
    `min_interval` seconds apart."""
    def __init__(self, min_interval):
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self):
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self._last = time.monotonic()


_GREENHOUSE_LIMITER = RateLimiter(0.15)   # ~6-7 req/sec ceiling
_ASHBY_LIMITER = RateLimiter(0.6)         # ~100/min budget, so stay under ~1.67/sec
_LEVER_LIMITER = RateLimiter(0.15)        # well under the documented 10/sec Data API limit
_WORKDAY_REQUEST_DELAY = 1.0              # per-tenant pacing, not shared across tenants

# Thread pool sizes per source, used by main(). Concurrency multiplies
# throughput up to the point the RateLimiter above starts gating it --
# e.g. Ashby's limiter alone caps total dispatch rate regardless of pool
# size, so its pool just needs to be big enough to keep that rate saturated
# while responses are in flight.
POOL_SIZES = {"greenhouse": 8, "ashby": 4, "lever": 6, "workday": 8}


# ---------------------------------------------------------------------------
# FETCH -- Greenhouse (uses ?live=true so only active, open roles return)
# ---------------------------------------------------------------------------

def fetch_greenhouse_jobs(company):
    """Returns (status, jobs). status is "ok" (board exists, jobs may be
    empty), "not_found" (bad token -- 404), or "error" (couldn't verify,
    e.g. a timeout)."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs?live=true"
    try:
        _GREENHOUSE_LIMITER.wait()
        req = urllib.request.Request(url, headers={"User-Agent": "job-agent/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
            jobs = data.get("jobs", [])
            print(f"  [greenhouse] {company}: {len(jobs)} live jobs found")
            normalized = []
            for job in jobs:
                normalized.append({
                    "id": f"gh_{job.get('id')}",
                    "source": "greenhouse",
                    "company": company,
                    "title": job.get("title", ""),
                    "location": (job.get("location") or {}).get("name", ""),
                    "url": job.get("absolute_url", ""),
                    "description": job.get("content", "") or "",
                    "posted_date": _parse_date_to_str(job.get("first_published") or job.get("updated_at")),
                })
            return "ok", normalized
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"  ! [greenhouse] {company}: board not found (404) - check token")
            return "not_found", []
        print(f"  ! [greenhouse] {company}: HTTP error {e.code}")
        return "error", []
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"  ! [greenhouse] {company}: connection error - {e}")
        return "error", []  # couldn't verify; don't touch closed-status for this company


# ---------------------------------------------------------------------------
# FETCH -- Ashby (public posting-api, no auth, only returns published posts)
# ---------------------------------------------------------------------------

def fetch_ashby_jobs(company):
    """Returns (status, jobs) -- see fetch_greenhouse_jobs for status values."""
    url = f"https://api.ashbyhq.com/posting-api/job-board/{company}?includeCompensation=false"
    try:
        _ASHBY_LIMITER.wait()
        req = urllib.request.Request(url, headers={"User-Agent": "job-agent/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
            jobs = data.get("jobs", [])
            print(f"  [ashby] {company}: {len(jobs)} published jobs found")
            normalized = []
            for job in jobs:
                # Ashby gives an explicit isRemote flag -- fold that into location
                # so our existing location_matches() keyword check still works.
                location = job.get("location", "") or ""
                if job.get("isRemote"):
                    location = f"Remote - {location}" if location else "Remote"
                normalized.append({
                    "id": f"ashby_{company}_{job.get('jobUrl', job.get('title', ''))}",
                    "source": "ashby",
                    "company": company,
                    "title": job.get("title", ""),
                    "location": location,
                    "url": job.get("jobUrl", job.get("applyUrl", "")),
                    "description": job.get("descriptionPlain", "") or "",
                    "posted_date": _parse_date_to_str(job.get("publishedAt")),
                })
            return "ok", normalized
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"  ! [ashby] {company}: board not found (404) - check token")
            return "not_found", []
        print(f"  ! [ashby] {company}: HTTP error {e.code}")
        return "error", []
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"  ! [ashby] {company}: connection error - {e}")
        return "error", []


# ---------------------------------------------------------------------------
# FETCH -- Lever (public postings API, no auth, only returns published posts)
# ---------------------------------------------------------------------------

def fetch_lever_jobs(company):
    """Returns (status, jobs) -- see fetch_greenhouse_jobs for status values."""
    url = f"https://api.lever.co/v0/postings/{company}?mode=json"
    try:
        _LEVER_LIMITER.wait()
        req = urllib.request.Request(url, headers={"User-Agent": "job-agent/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            jobs = json.loads(resp.read().decode())
            print(f"  [lever] {company}: {len(jobs)} published jobs found")
            normalized = []
            for job in jobs:
                categories = job.get("categories", {}) or {}
                location = categories.get("location", "") or ""
                workplace_type = job.get("workplaceType", "")
                if workplace_type == "remote" and "remote" not in location.lower():
                    location = f"Remote - {location}" if location else "Remote"
                normalized.append({
                    "id": f"lever_{company}_{job.get('id')}",
                    "source": "lever",
                    "company": company,
                    "title": job.get("text", ""),
                    "location": location,
                    "url": job.get("hostedUrl", job.get("applyUrl", "")),
                    "description": job.get("descriptionPlain", "") or "",
                    "posted_date": _parse_date_to_str(job.get("createdAt"), is_epoch_ms=True),
                })
            return "ok", normalized
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"  ! [lever] {company}: board not found (404) - check token")
            return "not_found", []
        print(f"  ! [lever] {company}: HTTP error {e.code}")
        return "error", []
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"  ! [lever] {company}: connection error - {e}")
        return "error", []


# ---------------------------------------------------------------------------
# FETCH -- Workday (public CXS JSON API, no auth -- but unlike the other
# boards, a tenant alone isn't enough to query it: needs the wd-subdomain
# number and site slug from WORKDAY_COMPANIES too). Searches per keyword
# server-side since a big tenant can have thousands of postings;
# title_matches() in process_jobs() re-verifies each result since Workday's
# searchText does a loose full-text match, not an exact one.
# ---------------------------------------------------------------------------

def fetch_workday_jobs(tenant):
    """Returns (status, jobs) -- see fetch_greenhouse_jobs for status values."""
    config = WORKDAY_COMPANIES.get(tenant)
    if not config:
        return "not_found", []
    wd, site = config["wd"], config["site"]
    base = f"https://{tenant}.{wd}.myworkdayjobs.com"
    url = f"{base}/wday/cxs/{tenant}/{site}/jobs"
    normalized = []
    seen_paths = set()
    first_request = True
    try:
        for keyword in TITLE_KEYWORDS:
            offset = 0
            for _ in range(3):  # cap pagination per keyword -- niche titles, not the full board
                # Pacing is per-tenant only (this function call, this thread)
                # -- Workday tenants are separate hosts, so this never blocks
                # other tenants running concurrently in main()'s thread pool.
                if first_request:
                    first_request = False
                else:
                    time.sleep(_WORKDAY_REQUEST_DELAY)
                payload = json.dumps({
                    "appliedFacets": {}, "limit": 20, "offset": offset, "searchText": keyword,
                }).encode()
                req = urllib.request.Request(url, data=payload, headers={
                    "Content-Type": "application/json", "User-Agent": "job-agent/1.0",
                })
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = json.loads(resp.read().decode())
                postings = data.get("jobPostings", [])
                for job in postings:
                    path = job.get("externalPath", "")
                    if not path or path in seen_paths:
                        continue
                    seen_paths.add(path)
                    location = job.get("locationsText", "")
                    if not location:
                        # Workday often leaves locationsText blank (especially
                        # for multi-location reqs), but externalPath always
                        # embeds the specific office as its own path segment,
                        # e.g. "/job/Barcelona-La-Rotonda/Kyriba-..._R123" --
                        # use that instead of losing the location entirely.
                        segments = [s for s in path.split("/") if s]
                        if len(segments) >= 2:
                            location = segments[1].replace("-", " ")
                    normalized.append({
                        "id": f"workday_{tenant}_{path}",
                        "source": "workday",
                        "company": tenant,
                        "title": job.get("title", ""),
                        "location": location,
                        "url": f"{base}/{site}{path}",
                        # Full description needs a second per-job request, so
                        # it's left blank here to keep this search cheap
                        # across a whole tenant -- fetch_workday_job_description()
                        # fills it in lazily, only for postings that pass every
                        # filter and are new (see process_jobs() in main()).
                        "description": "",
                        "external_path": path,
                        # Workday's list endpoint only ever gives a relative
                        # string here ("Posted 5 Days Ago", "Posted Today"),
                        # not an exact date -- getting the real date needs a
                        # second per-job request, skipped for the same
                        # request-count reasons as description above.
                        "posted_date": job.get("postedOn", ""),
                    })
                if len(postings) < 20:
                    break
                offset += 20
        print(f"  [workday] {tenant}: {len(normalized)} matching postings found")
        return "ok", normalized
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"  ! [workday] {tenant}: board not found (404) - check tenant/wd/site")
            return "not_found", []
        print(f"  ! [workday] {tenant}: HTTP error {e.code}")
        return "error", []
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"  ! [workday] {tenant}: connection error - {e}")
        return "error", []


def fetch_workday_job_description(tenant, external_path):
    """Best-effort fetch of the full description for ONE specific Workday
    posting, via the same per-job detail endpoint the public careers page
    itself calls (a plain GET against the posting's own externalPath, on the
    same host as the search endpoint). Deliberately not called for every
    posting the search step scans -- only from process_jobs() in main(),
    for postings that already passed every filter and are being scored for
    the first time, so this adds a handful of extra requests per run rather
    than one per posting on the tenant. Returns "" on any failure -- a
    missing description just means score_role() has less to work with, it
    should never break the run."""
    config = WORKDAY_COMPANIES.get(tenant)
    if not config or not external_path:
        return ""
    wd, site = config["wd"], config["site"]
    url = f"https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{external_path}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "job-agent/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
        return data.get("jobPostingInfo", {}).get("jobDescription", "") or ""
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as e:
        print(f"  ! [workday] {tenant}: couldn't fetch description for {external_path} - {e}")
        return ""


# ---------------------------------------------------------------------------
# FETCH -- Workable (cross-customer meta-search at jobs.workable.com;
# searches ALL Workable customers at once, so no company token list needed)
# ---------------------------------------------------------------------------

def _workable_field(job, *names, default=""):
    """Defensive getter: raw search-API field names aren't fully documented,
    so try several plausible names before giving up. Also unwraps nested
    objects (e.g. company can come back as {"name": "...", "id": "..."}
    instead of a plain string) since sqlite can't bind a dict directly."""
    for n in names:
        v = job.get(n)
        if v:
            if isinstance(v, dict):
                v = v.get("name") or v.get("title") or v.get("id") or ""
                if v:
                    return str(v)
                continue
            return str(v)
    return default


def fetch_workable_search(query):
    """Search all Workable customers for a query, remote roles only.
    Returns normalized jobs, or None on a connection error."""
    normalized = []
    page_token = None
    try:
        for _ in range(WORKABLE_MAX_PAGES_PER_QUERY):
            params = {"query": query, "workplace": "remote"}
            if page_token:
                params["nextPageToken"] = page_token
            url = "https://jobs.workable.com/api/v1/jobs?" + urllib.parse.urlencode(params)
            req = urllib.request.Request(url, headers={"User-Agent": "job-agent/1.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode())
            jobs = data.get("jobs", [])
            for job in jobs:
                company = _workable_field(job, "companyName", "company", default="unknown")
                # Location may be a string, a dict, or split fields depending
                # on response version -- handle all defensively.
                loc = job.get("location")
                if isinstance(loc, dict):
                    location = _workable_field(loc, "fullLocation", "location_str", "city")
                    country = _workable_field(loc, "country", "countryCode")
                    if country and country not in location:
                        location = f"{location}, {country}" if location else country
                else:
                    location = loc or _workable_field(job, "fullLocation", "city", "country")
                if job.get("remote") or job.get("isRemote") or job.get("workplace") == "remote":
                    if "remote" not in (location or "").lower():
                        location = f"Remote - {location}" if location else "Remote"
                job_key = _workable_field(job, "id", "uuid", "shortcode") or f"{company}_{job.get('title','')}"
                normalized.append({
                    "id": f"workable_{job_key}",
                    "source": "workable",
                    "company": company,
                    "title": job.get("title", ""),
                    "location": location or "",
                    "url": _workable_field(job, "url", "applyUrl", "shortlink"),
                    "description": _workable_field(job, "description", "descriptionText", "descriptionHtml"),
                    "posted_date": _parse_date_to_str(_workable_field(job, "published_on", "published", "created_at")),
                })
            page_token = data.get("nextPageToken")
            if not page_token or not jobs:
                break
        print(f"  [workable] search '{query}': {len(normalized)} remote jobs found")
        return normalized
    except urllib.error.HTTPError as e:
        print(f"  ! [workable] search '{query}': HTTP error {e.code}")
        return None
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"  ! [workable] search '{query}': connection error - {e}")
        return None


def matched_keywords(title):
    """All configured keywords that appear in the title, in TITLE_KEYWORDS
    order. Empty list means no match."""
    t = title.lower()
    return [kw for kw in TITLE_KEYWORDS if kw in t]


def title_matches(title):
    return bool(matched_keywords(title))


def _has_word(text, phrase):
    """Whole-phrase match with word boundaries, so e.g. "india" never matches
    inside "Indianapolis" and "us" never matches inside "Brussels"."""
    return re.search(r'(?<![a-zA-Z])' + re.escape(phrase) + r'(?![a-zA-Z])', text) is not None


def location_matches(location, title="", url=""):
    """
    True if a role looks like it's actually open to a Chicago/Illinois-based
    candidate. Checks location, title, AND url together, because several
    boards (Workable in particular) leave `location` as a bare "Remote" and
    only put the real country in the job title or url slug, e.g.
    ".../remote-technical-project-manager-in-india-at-ajaia" or a title of
    "Technical Project Manager (LATAM)".
    """
    if not location:
        # No location data supplied by the board at all -- nothing to judge
        # this on, so don't reject it just because the title/url don't
        # happen to mention Chicago/remote/US.
        return True

    combined = " ".join(filter(None, [location, title, url])).lower()
    combined = _strip_accents(combined)
    # Normalize url-slug separators to spaces so multi-word markers like
    # "south africa" match a slug's "south-africa".
    combined = re.sub(r'[-_/]+', ' ', combined)

    # Reject anything tied to a non-US country, region acronym, or a
    # well-known unambiguous foreign city -- even though "remote" alone
    # would otherwise match. Scanned broadly (location+title+url) since none
    # of these ordinarily collide with everyday English words.
    for phrase, cc in COUNTRY_NAMES.items():
        if cc != "US" and _has_word(combined, phrase):
            return False
    if any(_has_word(combined, r) for r in REGION_MARKERS):
        return False
    if any(_has_word(combined, c) for c in SAFE_BROAD_CITIES):
        return False

    if _has_word(combined, "chicago") or _has_word(combined, "illinois"):
        return True

    # Explicit "this is the US" markers -- NOT the same as a named state (a
    # named state is handled separately below, since a bare "remote" role
    # tied to one specific other state is a different case: restricted to
    # that state, not nationwide).
    is_explicit_us = (
        any(_has_word(combined, m) for m in US_EXPLICIT_MARKERS)
        or _has_word(combined, "us")
    )
    has_named_us_state = any(_has_word(combined, s) for s in US_STATE_NAMES)
    has_us_state_abbrev = any(
        m.group(1) in US_STATE_ABBREVS for m in re.finditer(r',\s*([a-z]{2})\b', combined)
    )

    # Comprehensive city/country lookup (geonamescache), restricted to the
    # location field itself -- title/url free text is too likely to
    # coincidentally match one of ~35,000 city names (see SAFE_BROAD_CITIES
    # comment above). A city ambiguous with a US place (Birmingham, St.
    # Louis, ...) only counts as foreign when nothing else here confirms US.
    location_norm = re.sub(r'[-_/]+', ' ', _strip_accents(location.lower()))
    city_verdict = find_place_signal(location_norm)
    if city_verdict == "foreign" and not (is_explicit_us or has_named_us_state or has_us_state_abbrev):
        return False

    is_remote = _has_word(combined, "remote")

    if is_remote:
        # A "remote" role that names one specific *other* US state, and never
        # mentions Illinois/Chicago or the country generally, is usually
        # restricted to that state's residents -- not actually open
        # nationwide, so it's a false positive for a Chicago-based search.
        if has_named_us_state and not is_explicit_us:
            return False
        # Same idea at the city level: e.g. "Remote - San Francisco" with
        # nothing else confirming nationwide scope.
        if city_verdict == "us" and not is_explicit_us:
            return False
        return True

    # Not remote and not Chicago/IL: a specific named US state/city (e.g.
    # "Milwaukee, Wisconsin, United States") means this is an onsite role
    # somewhere else -- not open to a Chicago-based candidate just because
    # "United States" is also in the string. Only a bare "United States"/
    # "USA" with nothing more specific stays permissive (some boards use
    # that alone, with no city, to mean nationwide).
    if has_named_us_state or has_us_state_abbrev or city_verdict == "us":
        return False

    return is_explicit_us


def is_priority_match(title, location):
    """Hybrid roles based in Chicago/Illinois get top billing in matches.md --
    a local hybrid role is the best-fit outcome for this search, ahead of
    fully-remote roles open to anyone nationwide."""
    combined = f"{title or ''} {location or ''}".lower()
    return (
        (_has_word(combined, "chicago") or _has_word(combined, "illinois"))
        and _has_word(combined, "hybrid")
    )


# Company tokens sourced directly from a LinkedIn network export -- i.e. you
# have an actual contact working there, not just "this looks like a
# plausible SaaS company to search." Kept separate from the CONFIRMED/
# auto-discovered/Contentsquare-partner-catalog blocks above, which aren't
# personal-network-sourced. If you add more network contacts later, add
# their company's token here too.
IN_NETWORK_COMPANIES = {
    # --- Greenhouse: from LinkedIn network export ---
    "contentsquare", "quantummetric", "newrelic", "pendo", "anthropic",
    "spoton", "semrush", "scylladb", "rapidsos", "tripleseat", "instrumentl",
    "optibus", "zerohash", "confluent", "grindr", "revenuewell", "datastax",
    "authenticx", "compound", "kin", "tealium", "yello", "redfin",
    "coreweave", "typeface", "doppel", "origamirisk", "liveramp", "imgix",
    "dust", "jiko", "specright", "dreamdata", "firstdue", "vantaca",
    "aclaimant", "allegrow", "amperity", "apiture", "avature", "basis",
    "beyondfinance", "boomi", "censys", "cision", "comply", "conversica",
    "conviva", "coupa", "cyncly", "dealhub", "franconnect", "genesys",
    "icapital", "knotch", "logiwa", "momentive", "nearmap", "ncino",
    "nuvei", "opploans", "qualtrics", "questsoftware", "safetyculture",
    "sitecore", "smartlinx", "softchoice", "usertesting", "voltus",
    "waitwhile", "wunderkind", "yext", "zywave", "rula", "papa",
    "pieinsurance", "sdocs", "qbench",

    # --- Ashby: from LinkedIn network ---
    "pushsecurity", "seasoned",
}


def is_in_network(company):
    """True if a LinkedIn contact works at this company -- checked by
    Greenhouse/Ashby/Lever/Workday token, so it's meaningful for those
    sources but never matches Workable (cross-customer search has no
    token list to check against -- its "company" is just a display name)."""
    return (company or "").strip().lower() in IN_NETWORK_COMPANIES


# ---------------------------------------------------------------------------
# SCORE (optional -- only runs if ANTHROPIC_API_KEY and RESUME_TEXT are set)
# Jobscan-style weighted breakdown instead of a single opaque number, so you
# can see WHY a role scored the way it did and which keywords to add.
# ---------------------------------------------------------------------------

def score_role(title, company, description):
    """Returns (score, detail_string), or (None, None) if scoring isn't
    configured or the API call fails."""
    if not ANTHROPIC_API_KEY or not RESUME_TEXT:
        return None, None

    prompt = f"""You are an ATS match analyzer that scores resumes against job descriptions the same way Jobscan does. Compare the RESUME to the JOB below and return ONLY valid JSON (no markdown fencing, no explanation) with exactly this shape:

{{"title_match": <0-100>, "keyword_match": <0-100>, "experience_fit": <0-100>, "domain_match": <0-100>, "education_certs": <0-100>, "missing_keywords": ["...", "..."]}}

- title_match: how closely the job title matches the candidate's title/seniority history
- keyword_match: how many of the job description's hard skills/tools/keywords appear in the resume
- experience_fit: years and type of experience required vs. what the resume shows
- domain_match: industry/domain overlap (e.g. SaaS, fintech, implementation/professional services)
- education_certs: education and certification requirements vs. resume
- missing_keywords: up to 8 important keywords from the job description that are NOT in the resume

RESUME:
{RESUME_TEXT[:6000]}

JOB ({title} at {company}):
{description[:6000]}"""

    payload = json.dumps({
        "model": CLAUDE_MODEL,
        # claude-sonnet-5 runs adaptive thinking by default, and thinking
        # tokens count against max_tokens -- 500 was only enough for the
        # final JSON answer with zero room for that, so most calls either
        # got cut off entirely still inside the thinking block (no text
        # block at all) or truncated mid-JSON. effort "low" keeps thinking
        # brief for this simple classification task, and 4096 leaves
        # headroom so neither the thinking nor the JSON answer gets cut off.
        "max_tokens": 4096,
        "output_config": {"effort": "low"},
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            if data.get("type") == "error":
                raise ValueError(f"API error: {data.get('error', {}).get('message', data)}")
            # Don't assume content[0] is the text block -- some models put a
            # "thinking" block (or other non-text block) first, and indexing
            # blindly raises KeyError: 'text' with no useful context.
            blocks = data.get("content") or []
            text_block = next((b for b in blocks if b.get("type") == "text"), None)
            if text_block is None:
                block_types = [b.get("type") for b in blocks]
                raise ValueError(f"no text block in response (got block types: {block_types})")
            text = text_block["text"].strip()
            text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
            parsed = json.loads(text)

            title_match = int(parsed.get("title_match", 0) or 0)
            keyword_match = int(parsed.get("keyword_match", 0) or 0)
            experience_fit = int(parsed.get("experience_fit", 0) or 0)
            domain_match = int(parsed.get("domain_match", 0) or 0)
            education_certs = int(parsed.get("education_certs", 0) or 0)
            missing = parsed.get("missing_keywords") or []

            score = round(
                0.15 * title_match + 0.40 * keyword_match + 0.20 * experience_fit
                + 0.15 * domain_match + 0.10 * education_certs
            )
            detail = (
                f"title {title_match}% | keywords {keyword_match}% | "
                f"experience {experience_fit}% | domain {domain_match}% | "
                f"education {education_certs}%"
            )
            if missing:
                detail += " | missing: " + ", ".join(str(k) for k in missing[:8])
            return score, detail
    except Exception as e:
        print(f"  ! scoring failed for {title}: {e}")
        return None, None


def rescore_pending(conn, limit=None):
    """Re-fetch and score every already-recorded match that never got a
    real score (score_detail == '' -- found before scoring was configured,
    or during a MAX_SCORE_CALLS-capped run). Doesn't touch genuinely new
    postings; that's process_jobs()'s job via the normal full run.

    Descriptions aren't stored anywhere (see score_role()'s docs), so this
    re-fetches them -- but grouped by (source, company) or, for Workable's
    cross-customer search, by the keyword that originally matched, so a
    board with several pending rows is only hit once, not once per row.
    Matches the right posting back by URL. A posting no longer found there
    (closed/removed since) is left unscored rather than guessed at.
    """
    if not (ANTHROPIC_API_KEY and RESUME_TEXT):
        print("Scoring isn't configured (missing ANTHROPIC_API_KEY/RESUME_TEXT) -- nothing to rescore.")
        return 0

    rows = conn.execute(
        "SELECT job_id, source, company, title, url, matched_keyword FROM seen WHERE score_detail = ''"
    ).fetchall()
    if not rows:
        print("No unscored matches to rescore.")
        return 0

    by_greenhouse, by_ashby, by_lever, by_workable_query = {}, {}, {}, {}
    workday_rows = []
    for job_id, source, company, title, url, matched_keyword in rows:
        if source == "greenhouse":
            by_greenhouse.setdefault(company, True)
        elif source == "ashby":
            by_ashby.setdefault(company, True)
        elif source == "lever":
            by_lever.setdefault(company, True)
        elif source == "workable":
            by_workable_query.setdefault(matched_keyword, True)
        elif source == "workday":
            workday_rows.append((company, url))

    descriptions_by_url = {}

    for company in by_greenhouse:
        status, jobs = fetch_greenhouse_jobs(company)
        if status == "ok":
            descriptions_by_url.update({job["url"]: job["description"] for job in jobs})

    for company in by_ashby:
        status, jobs = fetch_ashby_jobs(company)
        if status == "ok":
            descriptions_by_url.update({job["url"]: job["description"] for job in jobs})

    for company in by_lever:
        status, jobs = fetch_lever_jobs(company)
        if status == "ok":
            descriptions_by_url.update({job["url"]: job["description"] for job in jobs})

    for query in by_workable_query:
        jobs = fetch_workable_search(query)
        if jobs:
            descriptions_by_url.update({job["url"]: job["description"] for job in jobs})

    for company, url in workday_rows:
        config = WORKDAY_COMPANIES.get(company)
        if not config:
            continue
        prefix = f"https://{company}.{config['wd']}.myworkdayjobs.com/{config['site']}"
        if url.startswith(prefix):
            descriptions_by_url[url] = fetch_workday_job_description(company, url[len(prefix):])

    rescored = 0
    for job_id, source, company, title, url, matched_keyword in rows:
        if limit is not None and rescored >= limit:
            print(f"Rescoring capped at {limit} call(s); {len(rows) - rescored} left for next time.")
            break
        if url not in descriptions_by_url:
            print(f"  ! rescore: couldn't find current posting for {title} at {company} ({source}) -- left unscored")
            continue
        score, detail = score_role(title, company, descriptions_by_url[url])
        if score is None:
            continue
        conn.execute("UPDATE seen SET score = ?, score_detail = ? WHERE job_id = ?", (score, detail, job_id))
        conn.commit()
        rescored += 1
        print(f"  + rescored [{score}%] {title} ({company}) [{source}]")

    return rescored


# ---------------------------------------------------------------------------
# WRITE RESULTS -- markdown file and a static HTML dashboard, both in the repo
# ---------------------------------------------------------------------------

def write_matches(all_matches):
    timestamp = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if not all_matches:
        content = f"# Job Matches\n\nLast checked: {timestamp}\n\nNo matches found yet.\n"
        with open(MATCHES_FILE, "w") as f:
            f.write(content)
        print("No matches at all. matches.md updated.")
        return

    active = [m for m in all_matches if not m.get("archived")]
    archived = [m for m in all_matches if m.get("archived")]
    new_today = [m for m in active if m["first_seen"] == today]
    previously_viewed = [m for m in active if m["first_seen"] != today]

    def render_roles(roles):
        if not roles:
            return ["*Nothing here.*\n"]
        lines = []
        sort_key = lambda x: (
            not is_priority_match(x["title"], x.get("location")),
            -(x["score"] or 0),
        )
        for m in sorted(roles, key=sort_key):
            score = f"{m['score']}%" if m["score"] else "not scored"
            priority_tag = "[HYBRID - CHICAGO] " if is_priority_match(m["title"], m.get("location")) else ""
            network_tag = "[NETWORK] " if is_in_network(m.get("company")) else ""
            heading_line = f"### {priority_tag}{network_tag}[{score}] {m['company']} – {m['title']} ({m['source']})"
            is_closed = m.get("status") == "closed"
            if is_closed:
                heading_line = f"~~{heading_line}~~"
            lines.append(heading_line)
            if is_in_network(m.get("company")):
                lines.append("- In network: Yes (you have a LinkedIn contact here)")
            lines.append(f"- Posted: {m.get('posted_date') or 'unknown'}")
            lines.append(f"- Date added: {m['first_seen']}")
            lines.append(f"- Location: {m.get('location') or 'Not specified'}")
            if m.get("score_detail"):
                lines.append(f"- Score detail: {m['score_detail']}")
            lines.append(f"- Link: {m['url']}")
            if is_closed:
                lines.append(f"- Status: Closed as of {m.get('closed_date') or 'unknown date'}")
            lines.append("")
        return lines

    def render_section(heading, roles):
        return [f"## {heading}\n"] + render_roles(roles)

    lines = [f"# Job Matches\n", f"Last checked: {timestamp}\n"]
    lines += render_section(f"New ({len(new_today)})", new_today)
    lines += render_section(f"Previously Viewed ({len(previously_viewed)})", previously_viewed)

    if archived:
        # Collapsed by default via <details> -- archived roles are meant to
        # be out of the way, not gone (that's what dismissed.txt is for).
        lines.append(f"<details>\n<summary>Archived ({len(archived)})</summary>\n")
        lines += render_roles(archived)
        lines.append("</details>\n")

    with open(MATCHES_FILE, "w") as f:
        f.write("\n".join(lines))
    print(
        f"Wrote {len(new_today)} new, {len(previously_viewed)} previously-viewed, "
        f"and {len(archived)} archived match(es) to {MATCHES_FILE}."
    )


def write_dashboard(all_matches):
    """Self-contained HTML dashboard (no build step) with client-side search,
    filtering, sorting, and per-row Archive/Delete buttons. All job data is
    embedded as JSON and rendered with textContent/attribute setters (never
    innerHTML on external text) so a job title or company name from a job
    board can't inject markup.

    Archive/Delete write DIRECTLY to this GitHub repo via the REST API,
    using a fine-grained personal access token the viewer pastes in once
    (stored only in that browser's localStorage -- never sent anywhere but
    api.github.com). Archive appends the job's URL to archived.txt; Delete
    appends it to dismissed.txt. Either way, the actual seen_jobs.db/
    matches.md update happens on the next real run of job_agent.py (the
    daily workflow, or triggered manually) -- the button click just commits
    the instruction; this page also removes/flags the row immediately in
    THIS browser tab so it doesn't require waiting for that to feel like it
    worked.
    """
    out_dir = os.path.dirname(DASHBOARD_FILE)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    records = []
    for m in all_matches:
        records.append({
            "company": m.get("company") or "",
            "title": m.get("title") or "",
            "source": m.get("source") or "",
            "location": m.get("location") or "Not specified",
            "url": m.get("url") or "",
            "score": m.get("score") or 0,
            "score_detail": m.get("score_detail") or "",
            "posted_date": m.get("posted_date") or "unknown",
            "first_seen": m.get("first_seen") or "",
            "status": m.get("status") or "open",
            "archived": bool(m.get("archived")),
            "priority": is_priority_match(m.get("title", ""), m.get("location")),
            "in_network": is_in_network(m.get("company")),
        })

    # Escaping "</" prevents a job title/description containing a literal
    # "</script>" from breaking out of the embedded JSON payload.
    jobs_json = json.dumps(records).replace("</", "<\\/")
    sources = sorted({r["source"] for r in records} | {"greenhouse", "ashby", "lever", "workday", "workable"})
    sources_json = json.dumps(sources)
    repo_json = json.dumps(GITHUB_REPO)
    branch_json = json.dumps(GITHUB_BRANCH)
    dismissed_path_json = json.dumps(DISMISSED_FILE)
    archived_path_json = json.dumps(ARCHIVED_FILE)

    html_doc = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Job Matches Dashboard</title>
<style>
  /* Explicit dark theme throughout -- every rule that sets a background
     also sets a matching text color, rather than relying on the browser's
     auto light/dark inversion (that mismatch was exactly why the Archive
     button and source badges rendered as unreadable white-on-white:
     they set a light background but left color to inherit the page's
     auto-dark text, which is also light). */
  body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0; padding: 1.5rem; max-width: 1200px; margin-inline: auto; background: #0d1117; color: #e6edf3; }
  a { color: #58a6ff; }
  h1 { font-size: 1.4rem; margin-bottom: 0.25rem; }
  .meta { color: #9198a1; font-size: 0.85rem; margin-bottom: 1rem; }
  .controls { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; margin-bottom: 1rem; }
  .controls input, .controls select { padding: 0.4rem 0.6rem; font-size: 0.9rem; background: #161b22; color: #e6edf3; border: 1px solid #30363d; border-radius: 4px; }
  .controls input[type="text"] { flex: 1 1 220px; }
  button { font: inherit; cursor: pointer; }
  .btn { padding: 0.3rem 0.6rem; font-size: 0.8rem; border-radius: 4px; border: 1px solid #30363d; background: #21262d; color: #e6edf3; }
  .btn:hover { background: #30363d; }
  .btn:disabled { opacity: 0.5; cursor: default; }
  .btn-danger { border-color: #f85149; color: #f85149; }
  .btn-danger:hover { background: #3d1418; }
  table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
  th, td { text-align: left; padding: 0.5rem 0.6rem; border-bottom: 1px solid #30363d; vertical-align: top; }
  th { cursor: pointer; user-select: none; white-space: nowrap; }
  tr.priority td:first-child { border-left: 3px solid #2ea043; padding-left: 0.4rem; }
  tr.closed { opacity: 0.5; text-decoration: line-through; }
  tr.archived-row { opacity: 0.6; }
  tr.pending-archive td { text-decoration: line-through; background: rgba(88, 166, 255, 0.15); color: #79c0ff; }
  tr.pending-delete td { text-decoration: line-through; background: rgba(248, 81, 73, 0.15); color: #f85149; }
  .badge { display: inline-block; padding: 0.1rem 0.4rem; border-radius: 4px; background: #21262d; color: #c9d1d9; font-size: 0.75rem; }
  .network-badge { background: #1f3a5f; color: #79c0ff; }
  .score-detail { font-size: 0.75rem; color: #9198a1; }
  a.title-link { color: inherit; }
  #count { color: #9198a1; font-size: 0.85rem; margin-bottom: 0.5rem; }
  .actions-cell { display: flex; gap: 0.35rem; white-space: nowrap; }
  #settingsPanel { display: none; border: 1px solid #30363d; border-radius: 6px; padding: 0.75rem; margin-bottom: 1rem; font-size: 0.85rem; max-width: 520px; background: #161b22; }
  #settingsPanel input[type="password"] { width: 100%; padding: 0.4rem; margin: 0.4rem 0; box-sizing: border-box; background: #0d1117; color: #e6edf3; border: 1px solid #30363d; border-radius: 4px; }
  #status { font-size: 0.85rem; margin-bottom: 0.75rem; min-height: 1.2em; }
  #status.error { color: #f85149; }
  #status.ok { color: #2ea043; }
</style>
</head>
<body>
<h1>Job Matches Dashboard</h1>
<div class="meta">Generated by job_agent.py -- edit keywords.txt / applied.txt on GitHub to change what shows up here. Use Archive/Delete below to manage roles from here directly.</div>

<div class="controls">
  <button class="btn" id="settingsToggle" type="button">&#9881; GitHub token</button>
  <input type="text" id="search" placeholder="Search title or company...">
  <select id="sourceFilter"><option value="">All sources</option></select>
  <select id="minScore">
    <option value="0">Any score</option>
    <option value="50">50%+</option>
    <option value="70">70%+</option>
    <option value="85">85%+</option>
  </select>
  <label><input type="checkbox" id="hideClosed" checked> Hide closed</label>
  <label><input type="checkbox" id="hideArchived" checked> Hide archived</label>
  <label><input type="checkbox" id="networkOnly"> In network only</label>
</div>

<div id="settingsPanel">
  <div>
    Archive/Delete write straight to this repo (<code id="repoName"></code>) via the GitHub API. That needs a
    <strong>fine-grained personal access token</strong> scoped to <em>only this repo</em>, with
    <strong>Contents: Read and write</strong> permission and nothing else. Create one at
    <a href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noopener noreferrer">github.com/settings/personal-access-tokens/new</a>.
    It's stored only in this browser (localStorage) -- never sent anywhere but api.github.com.
  </div>
  <input type="password" id="tokenInput" placeholder="github_pat_...">
  <div class="actions-cell">
    <button class="btn" id="saveToken" type="button">Save</button>
    <button class="btn btn-danger" id="clearToken" type="button">Clear saved token</button>
  </div>
</div>

<div id="status"></div>
<div id="count"></div>
<table>
  <thead>
    <tr>
      <th data-key="company">Company</th>
      <th data-key="in_network">Network</th>
      <th data-key="title">Title</th>
      <th data-key="source">Source</th>
      <th data-key="location">Location</th>
      <th data-key="score">Score</th>
      <th data-key="posted_date">Posted</th>
      <th data-key="first_seen">Added</th>
      <th>Actions</th>
    </tr>
  </thead>
  <tbody id="rows"></tbody>
</table>

<script>
const JOBS = __JOBS_JSON__;
const SOURCES = __SOURCES_JSON__;
const GITHUB_REPO = __REPO_JSON__;
const GITHUB_BRANCH = __BRANCH_JSON__;
const DISMISSED_PATH = __DISMISSED_PATH_JSON__;
const ARCHIVED_PATH = __ARCHIVED_PATH_JSON__;
const TOKEN_KEY = "jobagent_gh_pat";

document.getElementById("repoName").textContent = GITHUB_REPO;

const sourceFilter = document.getElementById("sourceFilter");
for (const s of SOURCES) {
  const opt = document.createElement("option");
  opt.value = s;
  opt.textContent = s;
  sourceFilter.appendChild(opt);
}

let sortKey = "score";
let sortDir = -1;

function getToken() {
  try { return localStorage.getItem(TOKEN_KEY) || ""; } catch (e) { return ""; }
}
function setToken(t) {
  try { localStorage.setItem(TOKEN_KEY, t); } catch (e) { /* private window etc -- token just won't persist */ }
}
function clearToken() {
  try { localStorage.removeItem(TOKEN_KEY); } catch (e) {}
}

const settingsToggle = document.getElementById("settingsToggle");
const settingsPanel = document.getElementById("settingsPanel");
const tokenInput = document.getElementById("tokenInput");
settingsToggle.addEventListener("click", function () {
  settingsPanel.style.display = settingsPanel.style.display === "block" ? "none" : "block";
  tokenInput.value = getToken();
});
document.getElementById("saveToken").addEventListener("click", function () {
  setToken(tokenInput.value.trim());
  setStatus("Token saved to this browser.", "ok");
  settingsPanel.style.display = "none";
});
document.getElementById("clearToken").addEventListener("click", function () {
  clearToken();
  tokenInput.value = "";
  setStatus("Token cleared.", "ok");
});

function setStatus(msg, kind) {
  const el = document.getElementById("status");
  el.textContent = msg || "";
  el.className = kind || "";
}

function currentFilters() {
  return {
    search: document.getElementById("search").value.trim().toLowerCase(),
    source: sourceFilter.value,
    minScore: parseInt(document.getElementById("minScore").value, 10) || 0,
    hideClosed: document.getElementById("hideClosed").checked,
    hideArchived: document.getElementById("hideArchived").checked,
    networkOnly: document.getElementById("networkOnly").checked,
  };
}

// --- GitHub Contents API helpers -------------------------------------------

async function ghGetFile(path) {
  const token = getToken();
  const resp = await fetch(
    "https://api.github.com/repos/" + GITHUB_REPO + "/contents/" + path + "?ref=" + GITHUB_BRANCH,
    { headers: { Authorization: "Bearer " + token, Accept: "application/vnd.github+json" } }
  );
  if (resp.status === 404) return { text: "", sha: null };
  if (!resp.ok) {
    const body = await resp.json().catch(function () { return {}; });
    throw new Error(body.message || ("GitHub GET failed (" + resp.status + ")"));
  }
  const data = await resp.json();
  const bytes = atob((data.content || "").replace(/\\n/g, ""));
  let text;
  try {
    text = decodeURIComponent(escape(bytes));
  } catch (e) {
    text = bytes;
  }
  return { text: text, sha: data.sha };
}

async function ghPutFile(path, text, sha, message) {
  const token = getToken();
  const encoded = btoa(unescape(encodeURIComponent(text)));
  const body = { message: message, content: encoded, branch: GITHUB_BRANCH };
  if (sha) body.sha = sha;
  const resp = await fetch(
    "https://api.github.com/repos/" + GITHUB_REPO + "/contents/" + path,
    {
      method: "PUT",
      headers: {
        Authorization: "Bearer " + token,
        Accept: "application/vnd.github+json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    }
  );
  if (!resp.ok) {
    const errBody = await resp.json().catch(function () { return {}; });
    const err = new Error(errBody.message || ("GitHub PUT failed (" + resp.status + ")"));
    err.status = resp.status;
    throw err;
  }
}

function appendUniqueLine(text, line) {
  const norm = line.trim().toLowerCase();
  const existing = text.split("\\n").map(function (l) { return l.trim().toLowerCase(); });
  if (existing.indexOf(norm) !== -1) return text;
  const sep = text.length === 0 || text.endsWith("\\n") ? "" : "\\n";
  return text + sep + line.trim() + "\\n";
}

function removeMatchingLine(text, line) {
  const norm = line.trim().toLowerCase();
  const kept = text.split("\\n").filter(function (l) {
    const t = l.trim();
    return t === "" || t.startsWith("#") || t.toLowerCase() !== norm;
  });
  return kept.join("\\n");
}

async function updateListFile(path, transform, commitMessage) {
  let attempt = 0;
  while (true) {
    attempt += 1;
    const current = await ghGetFile(path);
    const next = transform(current.text);
    try {
      await ghPutFile(path, next, current.sha, commitMessage);
      return;
    } catch (e) {
      // 409/422 usually means the file's sha moved between our GET and PUT
      // (e.g. another tab, or job_agent.py itself, committed in between).
      // Refetch and retry once; anything else (bad token, etc.) surfaces.
      if ((e.status === 409 || e.status === 422) && attempt < 2) continue;
      throw e;
    }
  }
}

// --- Row actions -------------------------------------------------------

async function archiveJob(job, btn, tr) {
  if (!getToken()) { setStatus("Add a GitHub token first (\\u2699 GitHub token above).", "error"); return; }
  btn.disabled = true;
  setStatus("Archiving \\u201c" + job.title + "\\u201d...");
  try {
    await updateListFile(
      ARCHIVED_PATH,
      function (text) { return appendUniqueLine(text, job.url); },
      "Archive " + job.company + " - " + job.title + " via dashboard"
    );
    job._pending = "archive";
    setStatus("Marked for archiving \\u2014 stays here struck through until the next job_agent.py run (scheduled or manual) actually applies it.", "ok");
    render();
  } catch (e) {
    setStatus("Couldn't archive: " + e.message, "error");
    btn.disabled = false;
  }
}

async function unarchiveJob(job, btn) {
  if (!getToken()) { setStatus("Add a GitHub token first (\\u2699 GitHub token above).", "error"); return; }
  btn.disabled = true;
  setStatus("Unarchiving \\u201c" + job.title + "\\u201d...");
  try {
    await updateListFile(
      ARCHIVED_PATH,
      function (text) { return removeMatchingLine(text, job.url); },
      "Unarchive " + job.company + " - " + job.title + " via dashboard"
    );
    job.archived = false;
    job._pending = null;
    setStatus("Unarchived. Fully applied on the next job_agent.py run.", "ok");
    render();
  } catch (e) {
    setStatus("Couldn't unarchive: " + e.message, "error");
    btn.disabled = false;
  }
}

async function deleteJob(job, btn, tr) {
  if (!getToken()) { setStatus("Add a GitHub token first (\\u2699 GitHub token above).", "error"); return; }
  if (!confirm("Delete \\u201c" + job.title + "\\u201d at " + job.company + "? This hides it for good -- it won't be re-added even if the board reposts it.")) return;
  btn.disabled = true;
  setStatus("Deleting \\u201c" + job.title + "\\u201d...");
  try {
    await updateListFile(
      DISMISSED_PATH,
      function (text) { return appendUniqueLine(text, job.url); },
      "Dismiss " + job.company + " - " + job.title + " via dashboard"
    );
    job._pending = "delete";
    setStatus("Marked for deletion \\u2014 stays here struck through until the next job_agent.py run (scheduled or manual) actually removes it.", "ok");
    render();
  } catch (e) {
    setStatus("Couldn't delete: " + e.message, "error");
    btn.disabled = false;
  }
}

async function restoreJob(job, btn, tr) {
  if (!getToken()) { setStatus("Add a GitHub token first (\\u2699 GitHub token above).", "error"); return; }
  btn.disabled = true;
  setStatus("Restoring \\u201c" + job.title + "\\u201d...");
  try {
    await updateListFile(
      DISMISSED_PATH,
      function (text) { return removeMatchingLine(text, job.url); },
      "Restore " + job.company + " - " + job.title + " via dashboard"
    );
    job._pending = null;
    setStatus("Restored.", "ok");
    render();
  } catch (e) {
    setStatus("Couldn't restore: " + e.message, "error");
    btn.disabled = false;
  }
}

// --- Rendering -----------------------------------------------------------

function render() {
  const f = currentFilters();
  let rows = JOBS.filter(function (j) {
    if (j._pending === "delete" || j._pending === "archive") return true;
    if (f.hideClosed && j.status === "closed") return false;
    if (f.hideArchived && j.archived) return false;
    if (f.networkOnly && !j.in_network) return false;
    if (f.source && j.source !== f.source) return false;
    if (f.minScore && (j.score || 0) < f.minScore) return false;
    if (f.search) {
      const hay = (j.title + " " + j.company).toLowerCase();
      if (hay.indexOf(f.search) === -1) return false;
    }
    return true;
  });

  rows.sort(function (a, b) {
    let av = a[sortKey], bv = b[sortKey];
    if (typeof av === "string") av = av.toLowerCase();
    if (typeof bv === "string") bv = bv.toLowerCase();
    if (av < bv) return -1 * sortDir;
    if (av > bv) return 1 * sortDir;
    return 0;
  });

  const tbody = document.getElementById("rows");
  tbody.textContent = "";
  document.getElementById("count").textContent = rows.length + " of " + JOBS.length + " match(es)";

  for (const j of rows) {
    const tr = document.createElement("tr");
    if (j.priority) tr.classList.add("priority");
    if (j.status === "closed") tr.classList.add("closed");
    if (j.archived) tr.classList.add("archived-row");
    if (j._pending === "delete") tr.classList.add("pending-delete");
    if (j._pending === "archive") tr.classList.add("pending-archive");

    const tdCompany = document.createElement("td");
    tdCompany.textContent = j.company;
    tr.appendChild(tdCompany);

    const tdNetwork = document.createElement("td");
    if (j.in_network) {
      const netBadge = document.createElement("span");
      netBadge.className = "badge network-badge";
      netBadge.textContent = "\\u2713 network";
      netBadge.title = "You have a LinkedIn contact here";
      tdNetwork.appendChild(netBadge);
    }
    tr.appendChild(tdNetwork);

    const tdTitle = document.createElement("td");
    let link = null;
    try {
      const u = new URL(j.url);
      if (u.protocol === "http:" || u.protocol === "https:") link = u.href;
    } catch (e) { link = null; }
    if (link) {
      const a = document.createElement("a");
      a.href = link;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.className = "title-link";
      a.textContent = j.title;
      tdTitle.appendChild(a);
    } else {
      tdTitle.textContent = j.title;
    }
    if (j.archived) {
      const tag = document.createElement("div");
      tag.className = "score-detail";
      tag.textContent = "Archived";
      tdTitle.appendChild(tag);
    }
    if (j.score_detail) {
      const detail = document.createElement("div");
      detail.className = "score-detail";
      detail.textContent = j.score_detail;
      tdTitle.appendChild(detail);
    }
    tr.appendChild(tdTitle);

    const tdSource = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = "badge";
    badge.textContent = j.source;
    tdSource.appendChild(badge);
    tr.appendChild(tdSource);

    const tdLocation = document.createElement("td");
    tdLocation.textContent = j.location;
    tr.appendChild(tdLocation);

    const tdScore = document.createElement("td");
    tdScore.textContent = j.score ? (j.score + "%") : "not scored";
    tr.appendChild(tdScore);

    const tdPosted = document.createElement("td");
    tdPosted.textContent = j.posted_date;
    tr.appendChild(tdPosted);

    const tdAdded = document.createElement("td");
    tdAdded.textContent = j.first_seen;
    tr.appendChild(tdAdded);

    const tdActions = document.createElement("td");
    tdActions.className = "actions-cell";

    if (j._pending === "delete") {
      const restoreBtn = document.createElement("button");
      restoreBtn.type = "button";
      restoreBtn.className = "btn";
      restoreBtn.textContent = "Restore";
      restoreBtn.addEventListener("click", function () { restoreJob(j, restoreBtn, tr); });
      tdActions.appendChild(restoreBtn);
    } else if (j._pending === "archive") {
      const undoArchiveBtn = document.createElement("button");
      undoArchiveBtn.type = "button";
      undoArchiveBtn.className = "btn";
      undoArchiveBtn.textContent = "Unarchive";
      undoArchiveBtn.addEventListener("click", function () { unarchiveJob(j, undoArchiveBtn); });
      tdActions.appendChild(undoArchiveBtn);
    } else {
      const archiveBtn = document.createElement("button");
      archiveBtn.type = "button";
      archiveBtn.className = "btn";
      archiveBtn.textContent = j.archived ? "Unarchive" : "Archive";
      archiveBtn.addEventListener("click", function () {
        if (j.archived) unarchiveJob(j, archiveBtn); else archiveJob(j, archiveBtn, tr);
      });
      tdActions.appendChild(archiveBtn);

      const deleteBtn = document.createElement("button");
      deleteBtn.type = "button";
      deleteBtn.className = "btn btn-danger";
      deleteBtn.textContent = "Delete";
      deleteBtn.addEventListener("click", function () { deleteJob(j, deleteBtn, tr); });
      tdActions.appendChild(deleteBtn);
    }

    tr.appendChild(tdActions);
    tbody.appendChild(tr);
  }
}

document.querySelectorAll("th[data-key]").forEach(function (th) {
  th.addEventListener("click", function () {
    const key = th.getAttribute("data-key");
    if (sortKey === key) {
      sortDir *= -1;
    } else {
      sortKey = key;
      sortDir = key === "score" ? -1 : 1;
    }
    render();
  });
});

["search", "sourceFilter", "minScore", "hideClosed", "hideArchived", "networkOnly"].forEach(function (id) {
  document.getElementById(id).addEventListener("input", render);
});

render();
</script>
</body>
</html>
"""
    html_doc = (
        html_doc.replace("__JOBS_JSON__", jobs_json)
        .replace("__SOURCES_JSON__", sources_json)
        .replace("__REPO_JSON__", repo_json)
        .replace("__BRANCH_JSON__", branch_json)
        .replace("__DISMISSED_PATH_JSON__", dismissed_path_json)
        .replace("__ARCHIVED_PATH_JSON__", archived_path_json)
    )

    with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
        f.write(html_doc)
    print(f"Wrote dashboard with {len(records)} match(es) to {DASHBOARD_FILE}.")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    conn = init_db()

    if RESCORE_ONLY:
        # Skip the full company/board scan entirely -- just fill in real
        # scores for matches already sitting in seen_jobs.db unscored.
        rescored = rescore_pending(conn, limit=MAX_SCORE_CALLS)
        print(f"Rescored {rescored} previously-unscored match(es).")
        prune_stale_matches(conn)
        remove_dismissed(conn, load_dismissed())
        apply_archived_flags(conn, load_archived())
        _write_outputs(conn)
        conn.close()
        print("Done.")
        return

    total_checked = 0
    score_calls_made = 0
    live_ids_by_company = {}  # (source, company) -> set of job_ids seen this run
    scoring_enabled = bool(ANTHROPIC_API_KEY and RESUME_TEXT)
    if scoring_enabled and MAX_SCORE_CALLS is not None:
        print(f"Scoring capped at {MAX_SCORE_CALLS} call(s) this run (MAX_SCORE_CALLS set).")

    all_sources = (
        [("greenhouse", c) for c in GREENHOUSE_COMPANIES]
        + [("ashby", c) for c in ASHBY_COMPANIES]
        + [("lever", c) for c in LEVER_COMPANIES]
        + [("workday", c) for c in WORKDAY_COMPANIES]
    )

    fetchers = {
        "greenhouse": fetch_greenhouse_jobs,
        "ashby": fetch_ashby_jobs,
        "lever": fetch_lever_jobs,
        "workday": fetch_workday_jobs,
    }

    dismissed_entries = load_dismissed()

    def process_jobs(jobs, source):
        nonlocal total_checked, score_calls_made
        for job in jobs:
            title = job["title"]
            job_id = job["id"]
            location = job["location"]
            url = job["url"]
            total_checked += 1

            matched = matched_keywords(title)
            if not matched:
                continue
            if not location_matches(location, title, url):
                continue
            if already_seen(conn, job_id):
                continue
            if is_dismissed({"url": url, "company": job["company"]}, dismissed_entries):
                # Dismissed via the dashboard's Delete button (or by hand in
                # dismissed.txt) -- never re-add it, even if the board
                # reposts the exact same URL under a new job_id.
                continue

            if scoring_enabled and MAX_SCORE_CALLS is not None and score_calls_made >= MAX_SCORE_CALLS:
                # Cap reached -- still record the match (same as running with
                # no ANTHROPIC_API_KEY at all), just skip the API call so a
                # test run can't blow past the number of calls you asked for.
                score, detail = None, None
            else:
                description = job["description"]
                if source == "workday" and not description and scoring_enabled:
                    # Lazy fetch: only for a posting that's new and already
                    # passed every filter, so scoring has real text to work
                    # with instead of just the title (see
                    # fetch_workday_job_description() for why this isn't done
                    # for every posting the search step scans).
                    description = fetch_workday_job_description(job["company"], job.get("external_path", ""))
                score, detail = score_role(title, job["company"], description)
                if scoring_enabled:
                    score_calls_made += 1

            mark_seen(
                conn, job_id, source, job["company"], title, url, location,
                score or 0, job.get("posted_date", ""), matched[0], detail or "",
            )
            print(f"  + NEW MATCH [{score}%] {title} ({location}) [{source}]")

    company_status = load_company_status()

    # Fetches run concurrently per source (see the RateLimiter/POOL_SIZES
    # block above fetch_greenhouse_jobs for why each source gets its own
    # pool size and per-host pacing). Only the network I/O happens off the
    # main thread -- record_company_status/mark_seen/score_role all still
    # run here on the main thread as each future completes, so the sqlite
    # connection and the Claude API calls are never touched concurrently.
    companies_by_source = {}
    for source, company in all_sources:
        companies_by_source.setdefault(source, []).append(company)

    for source in ("greenhouse", "ashby", "lever", "workday"):
        companies = companies_by_source.get(source, [])
        if not companies:
            continue
        pool_size = POOL_SIZES[source]
        print(f"Checking {len(companies)} {source} companies (up to {pool_size} concurrent)...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=pool_size) as executor:
            future_to_company = {executor.submit(fetchers[source], c): c for c in companies}
            for future in concurrent.futures.as_completed(future_to_company):
                company = future_to_company[future]
                try:
                    status, jobs = future.result()
                except Exception as e:
                    print(f"  ! [{source}] {company}: unexpected error - {e}")
                    status, jobs = "error", []
                record_company_status(company_status, source, company, status, len(jobs))
                if status != "ok":
                    # 404 or network/timeout error -- couldn't verify this company.
                    continue
                # Track live IDs so previously-found roles that vanished get marked closed.
                live_ids_by_company[(source, company)] = {job["id"] for job in jobs}
                process_jobs(jobs, source)

    save_company_status(company_status)

    # Workable runs in cross-customer search mode: no company list needed.
    # NOTE: search results can't reliably prove a role closed (ranking and
    # pagination caps mean absence isn't evidence), so Workable roles are
    # deliberately excluded from closed-status updates.
    workable_queries = WORKABLE_SEARCH_QUERIES or TITLE_KEYWORDS
    for query in workable_queries:
        print(f"Checking workable search: '{query}'...")
        jobs = fetch_workable_search(query)
        if jobs is None:
            continue
        process_jobs(jobs, "workable")

    print(f"\nChecked {total_checked} jobs across {len(GREENHOUSE_COMPANIES)} Greenhouse, "
          f"{len(ASHBY_COMPANIES)} Ashby, {len(LEVER_COMPANIES)} Lever, "
          f"{len(WORKDAY_COMPANIES)} Workday companies, "
          f"and {len(workable_queries)} Workable searches.")
    if scoring_enabled:
        cap_note = f" (capped at {MAX_SCORE_CALLS})" if MAX_SCORE_CALLS is not None else ""
        print(f"Made {score_calls_made} real scoring API call(s) this run{cap_note}.")

    update_closed_status(conn, live_ids_by_company)
    prune_stale_matches(conn)
    remove_dismissed(conn, dismissed_entries)
    apply_archived_flags(conn, load_archived())

    _write_outputs(conn)
    conn.close()
    print("Done.")


def _write_outputs(conn):
    """Shared tail of a normal run and a RESCORE_ONLY run: apply
    applied.txt, then regenerate matches.md and the dashboard."""
    all_matches = get_all_matches(conn)
    applied_entries = load_applied()
    if applied_entries:
        before = len(all_matches)
        all_matches = [m for m in all_matches if not is_applied(m, applied_entries)]
        hidden = before - len(all_matches)
        if hidden:
            print(f"Hid {hidden} match(es) already marked applied in {APPLIED_FILE}.")

    write_matches(all_matches)
    write_dashboard(all_matches)


if __name__ == "__main__":
    main()
