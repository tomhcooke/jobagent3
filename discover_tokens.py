#!/usr/bin/env python3
"""
Token discovery helper
-----------------------
Standalone, manual-run tool -- NOT used by daily.yml. Given a list of
(company name, website) pairs, tries to find a working Greenhouse, Ashby, or
Lever token for each by:

  1. Generating plausible token variants from the company name.
  2. Testing each variant directly against the three public ATS APIs
     (a live HTTP call doubles as validation -- there's no cheaper way to
     confirm a token than to actually ask the board for it).
  3. Falling back to scraping the company's careers page for a direct
     boards.greenhouse.io / jobs.ashbyhq.com / jobs.lever.co link if none
     of the guessed variants worked.

Prints a report of what it found, and can optionally splice newly-verified
tokens straight into job_agent.py's GREENHOUSE_COMPANIES / ASHBY_COMPANIES /
LEVER_COMPANIES lists (--write), appending under an
"Auto-discovered by discover_tokens.py" marker comment so re-runs don't
duplicate entries already added.

Usage:
    python discover_tokens.py                # just print a report
    python discover_tokens.py --write        # also edit job_agent.py in place

Edit the COMPANIES list below (or point --file at a text file of
"name, https://example.com" lines) with the companies you want to check.
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request

# Add companies here as (display name, website) tuples, or use --file.
COMPANIES = [
    # ("Example Corp", "https://example.com"),
]

HEADERS = {"User-Agent": "job-agent-token-discovery/1.0"}


def _get(url, timeout=15):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode(errors="replace")


def variants(name):
    """Generate plausible ATS token variants from a company's display name."""
    base = re.sub(r"[^a-z0-9]", "", name.lower())
    words = re.findall(r"[a-z0-9]+", name.lower())
    candidates = {base}
    if words:
        candidates.add("".join(words))
        candidates.add("-".join(words))
        candidates.add(words[0])
    # Strip common corporate suffixes and try again.
    for suffix in ("inc", "llc", "corp", "co", "hq", "technologies", "software"):
        if base.endswith(suffix) and len(base) > len(suffix):
            candidates.add(base[: -len(suffix)])
    return [c for c in candidates if c]


def try_greenhouse(token):
    try:
        status, body = _get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?live=true")
        data = json.loads(body)
        return isinstance(data.get("jobs"), list)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return False


def try_ashby(token):
    try:
        status, body = _get(f"https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=false")
        data = json.loads(body)
        return isinstance(data.get("jobs"), list)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return False


def try_lever(token):
    try:
        status, body = _get(f"https://api.lever.co/v0/postings/{token}?mode=json")
        data = json.loads(body)
        return isinstance(data, list)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return False


def scrape_careers_page(website):
    """Look for a direct ATS link embedded in the company's own site (careers
    page, footer, etc). Returns (platform, token) or (None, None)."""
    for path in ("", "/careers", "/jobs", "/about/careers"):
        try:
            _, body = _get(website.rstrip("/") + path, timeout=15)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            continue
        m = re.search(r"(?:boards|job-boards)\.greenhouse\.io/([a-zA-Z0-9_-]+)", body)
        if m:
            return "greenhouse", m.group(1)
        m = re.search(r"jobs\.ashbyhq\.com/([a-zA-Z0-9_-]+)", body)
        if m:
            return "ashby", m.group(1)
        m = re.search(r"jobs\.lever\.co/([a-zA-Z0-9_-]+)", body)
        if m:
            return "lever", m.group(1)
    return None, None


def discover(name, website):
    """Returns (platform, token) or (None, None)."""
    for token in variants(name):
        if try_greenhouse(token):
            return "greenhouse", token
        if try_ashby(token):
            return "ashby", token
        if try_lever(token):
            return "lever", token
    if website:
        return scrape_careers_page(website)
    return None, None


def load_companies_file(path):
    companies = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(",", 1)]
            name = parts[0]
            website = parts[1] if len(parts) > 1 else ""
            companies.append((name, website))
    return companies


LIST_NAMES = {
    "greenhouse": "GREENHOUSE_COMPANIES",
    "ashby": "ASHBY_COMPANIES",
    "lever": "LEVER_COMPANIES",
}
MARKER = "# --- Auto-discovered by discover_tokens.py ---"


def update_job_agent_file(found, job_agent_path="job_agent.py"):
    """Append newly-discovered tokens into the matching list in job_agent.py,
    under a marker comment so re-runs don't create duplicate entries."""
    with open(job_agent_path, encoding="utf-8") as f:
        text = f.read()

    by_platform = {}
    for name, platform, token in found:
        by_platform.setdefault(platform, []).append(token)

    for platform, tokens in by_platform.items():
        list_name = LIST_NAMES[platform]
        list_match = re.search(rf"{list_name} = \[", text)
        if not list_match:
            print(f"  ! could not find {list_name} in {job_agent_path} -- skipping")
            continue
        close_idx = text.index("\n]", list_match.end())

        existing_block = text[list_match.end():close_idx]
        already = set(re.findall(r'"([a-zA-Z0-9_-]+)"', existing_block))
        new_tokens = [t for t in tokens if t not in already]
        if not new_tokens:
            continue

        insertion = ""
        if MARKER not in existing_block:
            insertion += f"\n\n    {MARKER}\n"
        insertion += "    " + ", ".join(f'"{t}"' for t in new_tokens) + ","

        text = text[:close_idx] + insertion + text[close_idx:]

    with open(job_agent_path, "w", encoding="utf-8") as f:
        f.write(text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="Path to a 'name, website' text file, one per line")
    parser.add_argument("--write", action="store_true", help="Splice verified tokens into job_agent.py")
    parser.add_argument("--job-agent", default="job_agent.py")
    args = parser.parse_args()

    companies = load_companies_file(args.file) if args.file else COMPANIES
    if not companies:
        print("No companies to check -- edit COMPANIES in this file or pass --file.")
        sys.exit(1)

    found = []
    for name, website in companies:
        print(f"Checking {name}...")
        platform, token = discover(name, website)
        if platform:
            print(f"  -> {platform}: {token}")
            found.append((name, platform, token))
        else:
            print("  -> not found")

    print(f"\nFound {len(found)}/{len(companies)} companies.")
    if found and args.write:
        update_job_agent_file(found, args.job_agent)
        print(f"Wrote new tokens into {args.job_agent}.")


if __name__ == "__main__":
    main()
