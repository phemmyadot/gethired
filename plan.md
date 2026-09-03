# Plan: Learned title-keyword store for `JobTitleRoleScanner`

## Problem

`JobTitleRoleScanner` ([pipeline.py](backend/src/ingestion/pipeline.py)) classifies
`is_engineering_role` from two hardcoded sets:

```python
NON_ENGINEERING_TERMS = {"advocate", "advocacy", "community", "recruiting", ...}
ENGINEERING_TERMS = {"engineer", "engineering", "developer", ...}
```

When neither set matches a title, confidence is `"low"` and the job falls
through to `extract_ambiguous_job_metadata()` — an LLM call. Every such call
that resolves `is_engineering_role` cleanly (LLM says yes/no with reasonable
confidence) is a term the regex *could* have caught next time, but today that
signal is discarded once the job is classified — the term set never grows.

## Goal

Every time the LLM resolves an engineering-role ambiguity, persist the
title term(s) that made the title ambiguous, tagged with the LLM's verdict.
Over time, promote frequently-seen, consistently-resolved terms into the
regex scanner's working set (loaded from DB, not just the hardcoded
literals), so fewer titles need the LLM on subsequent runs — the same
"cache what's expensive, consult the cache first" pattern already used by
`DiscoveredAtsCompany` for ATS board tokens.

## Data model

New table, same shape/spirit as `DiscoveredAtsCompany`:

```python
class TitleKeywordSignal(Base):
    __tablename__ = "title_keyword_signals"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    term          = Column(String(100), nullable=False)   # normalized lowercase token/phrase
    verdict       = Column(String(20), nullable=False)     # "engineering" | "non_engineering"
    source        = Column(String(20), nullable=False, default="llm")  # "llm" | "manual"
    seen_count    = Column(Integer, nullable=False, default=1)   # times this term produced this verdict
    conflict_count = Column(Integer, nullable=False, default=0)  # times LLM gave the OPPOSITE verdict for this term
    first_seen_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at  = Column(DateTime, default=datetime.utcnow)
    promoted      = Column(Boolean, nullable=False, default=False)  # true once folded into the active regex set

    __table_args__ = (
        UniqueConstraint("term", "verdict", name="uq_title_keyword_term_verdict"),
    )
```

Why `term` + `verdict` as separate rows rather than one row per `term` with a
running score: a term can legitimately get conflicting verdicts from
different postings (e.g. "platform" appears in both "Platform Engineer" and
"Platform Support Specialist" — context-dependent). Keeping both rows lets
promotion logic see the conflict rate and refuse to promote ambiguous terms,
rather than averaging it away.

## Extraction: which term to attribute the LLM's verdict to

The LLM resolves a *title*, not a single term. To turn that into a
term-level signal, extract candidate terms from the ambiguous title the same
way `_matches_resume_title`/`JobTitleRoleScanner` already tokenize — split on
non-alphanumeric, drop stopwords/seniority words (`senior`, `sr`, `staff`,
`lead`, `of`, `the`, `and`, ...) — and record **every remaining term** against
the LLM's `is_engineering_role` verdict for that job. A multi-word title like
"Member of Technical Staff" yields terms `{member, technical, staff}` (after
stopword removal: `{member, technical}` — "staff" is already a seniority
stopword elsewhere in this codebase, worth reusing that exact list for
consistency). This is deliberately noisy at the term level; the promotion
step (below) is what filters noise out via repetition + consistency, not the
extraction step.

## Write path

In the classify loop (`run_ingestion`, pipeline.py), immediately after an
`extract_ambiguous_job_metadata()` call whose `is_engineering_role` came from
the LLM (i.e. `role_scan["confidence"] != "high"`):

1. Tokenize `job["title"]` into candidate terms (as above).
2. For each term, upsert `TitleKeywordSignal(term, verdict)`:
   - increment `seen_count` if the row exists,
   - increment `conflict_count` on the *opposite*-verdict row for the same
     `term` if it exists (so both rows' conflict counters track disagreement
     between them),
   - else insert a new row.
3. Batch this with the existing per-job `save_job` commit pattern — don't add
   a new commit point; append to the same transaction that's already closed
   after each classify iteration (see the `db.commit()` fixes already in
   `save_job`/the classify loop — this write must follow that same
   "commit before the next slow LLM call" discipline, not reopen the leak).

This write is small and synchronous-safe: it's a plain upsert, not a network
call, so it doesn't reintroduce the idle-in-transaction risk as long as it's
committed in the same breath as the job's own save.

## Promotion: growing the regex set

Promotion is a **separate, explicit step** — not automatic on every write —
so a single mislabeled LLM response can't immediately corrupt the live
scanner. Two options, pick one at implementation time:

- **A. Startup-time load**: `JobTitleRoleScanner.__init__` (or a module-level
  loader called once at process start / ingestion-run start) queries
  `TitleKeywordSignal` for rows meeting a promotion threshold — e.g.
  `seen_count >= 5 AND conflict_count == 0` (or `conflict_count / seen_count`
  below some small ratio, e.g. 10%, if occasional noise should be tolerated)
  — and merges promoted terms into `ENGINEERING_TERMS`/`NON_ENGINEERING_TERMS`
  in memory for that run. Marks `promoted = True` on read so a dashboard/log
  can show what's live. Simple, no separate job, but the set only grows
  between process restarts (fine, since this API already restarts fairly
  often in practice per this session's history).

- **B. Explicit promotion pass**: a small maintenance function
  (`promote_title_keywords(db)`), run on a schedule (alongside the existing
  scheduler in [scheduler.py](backend/src/scheduler.py)) or manually via a
  script/endpoint, that reads candidates past the threshold, writes them
  into a small `PromotedTitleKeyword` cache table (or just flips `promoted`
  on `TitleKeywordSignal` and the scanner queries `WHERE promoted = True`
  directly instead of the hardcoded set at all). Slightly more moving parts,
  but decouples "when do we trust a new term" from "when does the process
  happen to restart."

Recommendation: start with **A** (startup-time load, threshold check inline)
— it's the smaller change, reuses the existing hardcoded sets as the
always-on floor (DB-promoted terms are additive, never replace the floor),
and matches how `_confirmed_tokens()` already works for ATS company tokens
(read once per run, not continuously re-evaluated).

## Scanner change

```python
class JobTitleRoleScanner:
    def __init__(self, extra_engineering: set[str] = None, extra_non_engineering: set[str] = None):
        self.ENGINEERING_TERMS = self.ENGINEERING_TERMS | (extra_engineering or set())
        self.NON_ENGINEERING_TERMS = self.NON_ENGINEERING_TERMS | (extra_non_engineering or set())
    ...

def _load_promoted_terms(db) -> tuple[set[str], set[str]]:
    rows = db.query(TitleKeywordSignal).filter(
        TitleKeywordSignal.seen_count >= PROMOTION_MIN_SEEN,
        TitleKeywordSignal.conflict_count == 0,
    ).all()
    eng = {r.term for r in rows if r.verdict == "engineering"}
    non_eng = {r.term for r in rows if r.verdict == "non_engineering"}
    return eng, non_eng

# in run_ingestion, once per run (not per job):
extra_eng, extra_non_eng = _load_promoted_terms(db)
db.commit()  # close the read's transaction before the classify loop, per the leak-prevention pattern
scanner = JobTitleRoleScanner(extra_eng, extra_non_eng)
```

`TITLE_ROLE_SCANNER` stops being a module-level singleton constructed once at
import time and becomes constructed per-run instead (cheap — it's just two
set unions), so each run picks up whatever's been promoted since the last one.

## Non-goals / deferred

- **No automatic demotion.** If a promoted term starts conflicting later
  (new postings disagree with the old verdict), that shows up as
  `conflict_count` climbing on the *other*-verdict row, but nothing
  automatically un-promotes the original. Manual review only, for now —
  automatic demotion risks flapping.
- **No UI.** This plan is data-model + load-path only; a future pass could
  expose `TitleKeywordSignal` rows in an admin view for manual promote/reject,
  similar to how `DiscoveredAtsCompany` has no UI today either.
- **No cross-scanner reuse.** `JobWorkModeScanner`'s regexes are structural
  (phrase patterns like `"remote in the us"`), not single-term — this
  learning loop is specific to `JobTitleRoleScanner`'s term-membership
  design and doesn't generalize to work_mode without a different extraction
  strategy (phrase n-grams, not tokens).

## Files touched (when implemented)

- `backend/src/db/models.py` — add `TitleKeywordSignal`.
- `backend/src/ingestion/pipeline.py` — tokenize+upsert on LLM role
  resolution; `_load_promoted_terms()`; `JobTitleRoleScanner.__init__` takes
  extra sets; `run_ingestion` constructs the scanner per-run instead of using
  a module singleton.
- Manual one-time `ALTER TABLE`/`CREATE TABLE` against the dev DB, same as
  every other schema change this session — no migration tooling in this repo.
