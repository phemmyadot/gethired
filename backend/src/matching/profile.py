"""
Extract a search profile (keywords) from a resume via the LLM,
used to scope job ingestion to roles that actually match the candidate.
"""
import json
import logging

from ..llm import generate_text

logger = logging.getLogger(__name__)

PROFILE_PROMPT = """Read this resume and extract a job-search profile.

RESUME:
{resume_content}

Return ONLY valid JSON in this exact shape:
{{
  "search_keywords": "2-5 word search string for a job board, e.g. \\"senior backend engineer\\"",
  "required_keywords": ["skill_or_title_term_1", "skill_or_title_term_2"]
}}

"search_keywords" should be the single best job-title-style search string for this candidate.
"required_keywords" should be 2-5 lowercase terms (skills or title words) that a genuinely
relevant job posting for this person would almost always mention. Keep it short and precise."""


def extract_profile(resume_content: str) -> dict:
    """Derive search keywords and required keywords from a resume via the LLM."""
    default = {"search_keywords": "software engineer", "required_keywords": []}
    try:
        raw = generate_text(PROFILE_PROMPT.format(resume_content=resume_content[:4000]))
        profile = json.loads(raw)
    except Exception as e:
        logger.error(f"Profile extraction failed: {e}")
        return default

    return {
        "search_keywords": profile.get("search_keywords") or default["search_keywords"],
        "required_keywords": [k.lower() for k in profile.get("required_keywords", [])],
    }
