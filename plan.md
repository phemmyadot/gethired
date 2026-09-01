# Plan: Dynamic company discovery for Greenhouse / Lever / Ashby

## Problem
`GREENHOUSE_COMPANY_TOKENS` / `LEVER_COMPANY_TOKENS` are static, hand-maintained
env-var lists ([sources.py:278-348](backend/src/ingestion/sources.py#L278-L348)).
There's no free public directory mapping "companies hiring for X" to their ATS
board token, so the list never grows on its own and misses companies that would
otherwise be relevant to the current resume profile.

## Core idea
Adzuna / Remotive / RemoteOK / Jobicy / Arbeitnow already return real `company`
names on every ingestion run, scoped by the resume's search keywords
([pipeline.py](backend/src/ingestion/pipeline.py) `run_ingestion`). Treat those
company names as free candidate signal: probe whether each one also has a
Greenhouse/Lever/Ashby board, cache confirmed tokens, and feed them into the
existing `fetch_greenhouse_all` / `fetch_lever_all` (+ new `fetch_ashby_all`)
company lists — no LLM cost, just a handful of cheap HTTP HEAD/GET probes per
new company name.

## Architecture

### 1. New table: `discovered_ats_companies`
```
id            UUID PK
company_name  TEXT          -- raw name as seen from aggregator, e.g. "Notion Labs Inc."
source        TEXT          -- "greenhouse" | "lever" | "ashby"
board_token   TEXT NULL     -- confirmed slug if found, NULL if ruled out
status        TEXT          -- "confirmed" | "not_found" | "pending"
checked_at    TIMESTAMP
UNIQUE(company_name, source)
```
Alembic migration `0005_discovered_ats_companies.py`.

Storing both confirmed AND ruled-out (`not_found`) rows is required — otherwise
the same non-matching company gets re-probed (and re-404s) on every run
forever.

### 2. Slug candidate generation
New helper in `sources.py`:
```python
def _slug_candidates(company_name: str) -> list[str]:
    """e.g. 'Notion Labs, Inc.' -> ['notion-labs-inc', 'notion-labs', 'notion']"""
```
Strip common suffixes (Inc, LLC, Corp, Ltd, Co), lowercase, hyphenate, and also
try just the first word — covers the common cases (`Stripe` -> `stripe`,
`Notion Labs Inc.` -> `notion`) without over-engineering fuzzy matching.

### 3. Probe functions (one per ATS)
```python
def probe_greenhouse(slug: str) -> bool   # GET boards-api.greenhouse.io/v1/boards/{slug}/jobs, cheap, no LLM
def probe_lever(slug: str) -> bool        # GET api.lever.co/v0/postings/{slug}?mode=json
def probe_ashby(slug: str) -> bool        # GET api.ashbyhq.com/posting-api/job-board/{slug}
```
Each: short timeout (5s), treat any 2xx with a non-empty postings list as
confirmed, 404/empty as not_found. Try each slug candidate in order, stop at
first hit.

### 4. Discovery step in the ingestion pipeline
In `run_ingestion` ([pipeline.py](backend/src/ingestion/pipeline.py)), after
the aggregator fetch step and before pre-filtering:
```python
new_company_names = {j["company"] for j in all_raw if j["source"] in AGGREGATOR_SOURCES}
_discover_ats_companies(db, new_company_names, limit=20)  # rate-capped per run
```
`_discover_ats_companies`:
- Skip any `(company_name, source)` pair already in `discovered_ats_companies`.
- For the rest (capped at `limit` per run per source, e.g. 20), run the slug
  probe for each of greenhouse/lever/ashby.
- Write a `confirmed`/`not_found` row for every attempt (so it's never
  reprobed).
- This runs synchronously inline in ingestion for simplicity — probes are
  cheap (a few HTTP calls, no LLM), capped count keeps it bounded.

### 5. Wire confirmed tokens into fetch calls
```python
def _confirmed_tokens(db, source: str) -> list[str]:
    return [r.board_token for r in db.query(DiscoveredAtsCompany)
            .filter_by(source=source, status="confirmed")]
```
`fetch_greenhouse_all` / `fetch_lever_all` company list becomes:
`env-configured tokens + discovered confirmed tokens` (dedup, union).
New `fetch_ashby_all` follows the exact same pattern as the other two
(`fetch_ashby_company(token)` + `fetch_ashby_all(companies=None)`), gated by a
new `ASHBY_ENABLED` flag mirroring `GREENHOUSE_ENABLED`/`LEVER_ENABLED`.

### 6. Still respect existing feature flags
Discovery runs regardless of `GREENHOUSE_ENABLED`/`LEVER_ENABLED`/`ASHBY_ENABLED`
(cheap, no reason to gate it) — but **fetching** confirmed companies' full job
lists still only happens if that source's flag is on, same as today.

## Sequencing / rollout
1. Migration + `DiscoveredAtsCompany` model.
2. Slug generation + 3 probe functions + unit-testable in isolation.
3. Wire `_discover_ats_companies` into `run_ingestion`, capped at ~20/run.
4. Wire confirmed tokens into the 3 `fetch_*_all` company-list resolution.
5. Add `fetch_ashby_all` (new source, same shape as Greenhouse/Lever) +
   `ASHBY_ENABLED` flag + add `"ashby"` to `_default_sources()`.
6. Manual test: run ingestion once, confirm `discovered_ats_companies` fills
   with a mix of confirmed/not_found rows, confirm no perf regression on
   ingestion time from the added probes.

## Open questions to confirm before implementing
- Probe cap per run (suggested: 20 per source, ~60 total) — fine, or lower to
  be gentler on ingestion latency?
- Should `not_found` rows ever be retried (e.g. after 90 days, in case a
  company adds a board later)? Suggested: no retry for v1, revisit if needed.
- Ashby: same `ASHBY_ENABLED`-gated, opt-in-by-default-off pattern as
  Greenhouse/Lever, or enabled by default since it's read-only discovery?
