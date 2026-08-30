# TODO

## 1. Show ingestion progress
Currently `_run_full_pipeline` runs fully in a background task with no
intermediate state — the frontend just polls `/stats` after a fixed 3s
delay and hopes it's done. `IngestionLog` is only written once ingestion
completes, so there's nothing to show "in progress."

- Add a `PipelineRun` status row (or reuse `IngestionLog` with a `status`
  column: `running|done|failed`) created at the start of `_run_full_pipeline`,
  updated as each stage (ingest → match → apply) completes.
- Add `GET /pipeline/status` returning the current/last run's stage and
  counts so far.
- Frontend: poll `/pipeline/status` while `pipelineRunning` is true, show
  stage + counts in the sidebar instead of a static "Running…" label.

## 2. Only show matches >= 70% in Matches tab
`GET /matches` defaults to `min_score=0.0` ([routes.py:128](backend/src/api/routes.py#L128))
and the frontend calls `getMatches(0)` ([index.tsx](frontend/src/pages/index.tsx)),
so every scored job (including near-zero) shows up.

- Frontend: call `getMatches(0.7)` instead of `getMatches(0)`, or
- Backend: default `min_score` to `0.7` — decide which; frontend-side is
  less surprising since low scores are still useful data via the API.

## 3. Link to application from Matches / Jobs feed
- Matches tab: for a match with `applied: true`, add a "view application"
  link/button in `MatchesTab`/`MatchDrawer` that jumps to the Applications
  tab filtered to that `job_id` (needs a way to deep-link into a tab with
  a filter — simplest: lift a "focused application id" into root state).
- Jobs tab: same — if a job has an associated `AppliedJob`, show a link;
  otherwise nothing. Requires `GET /jobs` to include applied status
  (currently it doesn't join against `applied_jobs`).

## 4. Mark as applied from Matches / Jobs feed
- Already have `POST /matches/{job_id}/{resume_id}/apply` (manual apply,
  added earlier) which actually runs the apply flow (cover letter +
  submission). Confirm that's what's wanted here vs. a lighter-weight
  "just mark applied without auto-generating a cover letter / submitting."
- Jobs tab currently has no apply affordance at all — needs the match
  data joined in (a job might have multiple resume matches) or a resume
  picker if applying directly from Jobs feed.

## 5. Show user titles used for matching, in a box on Matches page
This refers to the `search_keywords` / `required_keywords` profile
extracted from the resume ([profile.py](backend/src/matching/profile.py))
that drives ingestion — currently computed on every pipeline run and
never persisted or exposed via the API.

- Persist the last-used profile (e.g. new columns on `Resume`, or a
  small `search_keywords`/`required_keywords` JSON field set after
  `extract_profile` runs) so it can be displayed later.
- Add `GET /profile` (or include on `/stats`) returning the current
  active resume's derived search keywords.
- Frontend: add a small info box at the top of `MatchesTab` showing
  those keywords/titles.

## Open questions before implementing
- Ingestion progress: reuse `IngestionLog` with a status column, or a
  separate lightweight table? reuse
- Score threshold: hardcode 0.7 on frontend call, or make it a documented
  constant shared between backend `SCORE_THRESHOLD` and frontend? SCORE_THRESHOLD
- "Mark as applied" — full apply flow (cover letter + submission) or a
  manual/lightweight status flip with no generation? apply button that generates a cover letter, user go to link to apply and copy cover letter from app to paste app application site. when they apply, they record apply in app
- Jobs feed apply/status: needs match data joined in — is Jobs feed
  meant to only show jobs with an existing match, or all ingested jobs
  regardless of match status? all ingested. matches will show only match >=70%
