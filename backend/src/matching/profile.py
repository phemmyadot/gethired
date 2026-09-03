"""
Extract a search profile (keywords) from a resume via the LLM,
used to scope job ingestion to roles that actually match the candidate.
"""
import json
import logging
import re

from ..llm import generate_text

logger = logging.getLogger(__name__)

# Deterministic fallback when the LLM can't produce usable required_keywords
# after retries (e.g. it keeps returning generic title words). Scanned
# directly against the resume text rather than relying on the model to pick
# good terms — a smaller but reliable list beats an LLM-generated list that
# might be empty or generic.
_KNOWN_TECH_TERMS = [
    "react native", "react", "typescript", "javascript", "node.js", "nodejs",
    "python", "java", "golang", "rust", "ruby", "rails", "php", "laravel",
    "django", "flask", "spring", ".net", "c#", "swift", "kotlin", "flutter",
    "aws", "azure", "gcp", "kubernetes", "docker", "terraform",
    "postgresql", "postgres", "mysql", "mongodb", "cosmosdb", "redis", "graphql",
    "next.js", "nextjs", "vue", "angular", "expo", "redux",
    "ci/cd", "jenkins", "github actions",
]


def _fallback_keywords_from_resume(resume_content: str) -> list[str]:
    resume_lower = resume_content.lower()
    found = [term for term in _KNOWN_TECH_TERMS if term in resume_lower]
    return found[:6]

PROFILE_PROMPT = """Read this resume and extract a job-search profile.

RESUME:
{resume_content}

Return ONLY valid JSON in this exact shape:
{{
  "search_keywords": "2-5 word search string for a job board, e.g. \\"senior backend engineer\\"",
  "required_keywords": ["skill_or_title_term_1", "skill_or_title_term_2", "skill_or_title_term_3", "skill_or_title_term_4"]
}}

"search_keywords" should be the single best job-title-style search string for this candidate.

"required_keywords" must be 3-6 lowercase CONCRETE TECHNOLOGY/SKILL terms pulled from the
resume's actual technical skills section or hands-on project work — e.g. "react", "typescript",
"aws", "node.js", "postgresql", "react native". These are used to filter job postings, so they
must be specific enough that a genuinely irrelevant job would NOT mention them.

NEVER use generic job-title or seniority words as required_keywords — words like "software",
"engineer", "developer", "senior", "full-stack", "full stack" appear in nearly every posting
regardless of relevance and make filtering useless. Bad example: ["software engineer", "senior"].
Good example: ["react", "typescript", "aws", "node.js"]."""


# Generic job-title/seniority words that make required_keywords useless as a
# filter — almost every posting for this candidate's level would mention
# them regardless of actual relevance, so pre_filter's "any keyword present"
# check becomes a near no-op if these slip through.
_GENERIC_KEYWORD_TERMS = {
    "software", "engineer", "engineering", "developer", "programmer",
    "senior", "junior", "mid", "mid-level", "staff", "principal", "lead",
    "full-stack", "full stack", "fullstack", "software engineer",
    "senior software engineer", "backend", "frontend", "front-end", "back-end",
}


def extract_profile(resume_content: str, retries: int = 3) -> dict | None:
    """
    Derive search keywords and required keywords from a resume via the LLM.
    Retries on failure since callers must not silently fall back to an
    empty required_keywords list — that disables pre_filter entirely.
    Also retries if every returned keyword is a generic title/seniority word
    (e.g. ["software engineer", "senior"]) — technically non-empty, but
    matches nearly any posting, defeating the point of the filter.
    Returns None only if every attempt fails.
    """
    for attempt in range(1, retries + 1):
        try:
            raw = generate_text(PROFILE_PROMPT.format(resume_content=resume_content[:4000]))
            profile = raw if isinstance(raw, dict) else json.loads(raw)
            search_keywords = profile.get("search_keywords")
            if not search_keywords:
                raise ValueError("no search_keywords in response")

            required_keywords = [k.lower().strip() for k in profile.get("required_keywords", []) if k]
            concrete_keywords = [
                k for k in required_keywords
                if k not in _GENERIC_KEYWORD_TERMS and len(k) > 3
            ]
            if len(concrete_keywords) < 2:
                raise ValueError(
                    f"required_keywords had too few concrete terms after filtering "
                    f"generic/short words: {required_keywords!r} -> {concrete_keywords!r}"
                )

            return {
                "search_keywords": search_keywords,
                "required_keywords": concrete_keywords,
            }
        except Exception as e:
            logger.warning(f"Profile extraction attempt {attempt}/{retries} failed: {e}")

    # LLM couldn't produce usable keywords across all retries — fall back to
    # scanning the resume for known tech terms rather than giving up (which
    # would force callers back to whatever profile was previously saved,
    # potentially stale or from a different resume).
    fallback_keywords = _fallback_keywords_from_resume(resume_content)
    if fallback_keywords:
        logger.warning(
            f"Profile extraction failed after {retries} LLM attempts; "
            f"using deterministic keyword fallback: {fallback_keywords!r}"
        )
        search_keywords_match = re.search(
            r"(senior|staff|principal|junior|lead)?\s*(software|full[- ]?stack|frontend|backend|mobile)\s*engineer",
            resume_content, re.IGNORECASE,
        )
        return {
            "search_keywords": (
                search_keywords_match.group(0).strip() if search_keywords_match
                else "software engineer"
            ),
            "required_keywords": fallback_keywords,
        }

    logger.error(f"Profile extraction failed after {retries} attempts, no fallback keywords found")
    return None
