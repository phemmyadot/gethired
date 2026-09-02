import json
import logging
import os
import re
import threading
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)
_LOCAL_LLM_LOCK = threading.Lock()


def _strip_reasoning_and_fences(text: str) -> str:
    """
    Reasoning models (e.g. deepseek-r1-distill-*) emit a <think>...</think>
    block before the actual answer, sometimes inline in `content` rather than
    in a separate `reasoning_content` field depending on the serving template.
    Non-reasoning models sometimes wrap JSON in markdown code fences, or add
    stray commentary before/after, despite being told not to. Extract the
    first {...} object rather than relying on stripping specific wrappers,
    since that's robust to whatever surrounds it.
    """
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    return match.group(0) if match else text


def _local_llm_base_url() -> str:
    return os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1").rstrip("/")


def _local_llm_model() -> str:
    return os.getenv("LOCAL_LLM_MODEL", "llama3.1")


def _local_llm_scoring_model() -> str:
    return os.getenv("LOCAL_LLM_SCORING_MODEL", "qwen2.5-7b-instruct")


def _local_llm_timeout() -> float:
    return float(os.getenv("LOCAL_LLM_TIMEOUT", "120"))

def parse_prefilled_response(raw_assistant_content: str) -> dict:
    # Prepend the pre-filled opening bracket to reconstruct complete JSON
    full_json_str = "{" + raw_assistant_content.strip()
    
    # Sanitize any residual trailing commas before closing braces/brackets
    sanitized_str = re.sub(r',\s*([\}\]])', r'\1', full_json_str)
    
    return json.loads(sanitized_str)

def parse_prefilled_completion(content: str) -> dict:
    """Reconstructs and parses JSON from an assistant response pre-filled with '</think>\\n{'."""
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    raw_str = content if content.startswith("{") else "{" + content
    
    # Clean up potential trailing commas prior to object/array closure
    sanitized = re.sub(r',\s*([\}\]])', r'\1', raw_str)
    
    # Some local servers append trailing text or a second object.
    return json.JSONDecoder().raw_decode(sanitized.lstrip())[0]

SYSTEM_PROMPT = """
You are an expert technical recruiter and candidate matcher. Evaluate only the
job description and candidate resume supplied in the current user message.
Never reuse, infer, or copy details from another job, candidate, or example.

Identify the job's primary functional discipline and the resume's primary
discipline. Ignore the employer's industry when it is unrelated to the role.
If the disciplines or scope do not match, set discipline_match to false or
scope_mismatch to true, and do not allow required_skills_pct, domain_fit_pct,
or seniority_fit_pct to exceed 20.

Extract the job's actual domain and required technology stack before comparing
the resume. Keep backend/systems, web, and mobile scopes distinct. Never label
a role as mobile or include React Native/mobile skills unless the job
description explicitly requires iOS, Android, React Native, or mobile apps.
Do not copy generic resume-summary phrases into the job skill fields.

Return only valid JSON with these fields:
job_discipline, resume_discipline, discipline_match, scope_mismatch,
discipline_and_scope_analysis, required_skills_pct, experience_years_pct,
domain_fit_pct, seniority_fit_pct, key_skills, missing_skills,
selling_points, seniority_fit, recommended_resume, reasoning.

key_skills must contain only concrete skills, technologies, or domains found
in the current job description. missing_skills must contain only explicit job
requirements not demonstrated in the resume. selling_points must describe
specific evidence of overlap and must not claim that a resume skill matches a
requirement that the job description does not state. All three fields must be
JSON arrays of strings. Use only evidence from the current job description and
resume.
"""


def build_local_messages(
    prompt: str,
    system_prompt: str | None = None,
    model: str | None = None,
) -> list[dict[str, str]]:
    """Build an isolated payload with a prefill only for reasoning models."""
    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    selected_model = model or _local_llm_model()
    if selected_model.lower().startswith("deepseek"):
        messages.append({"role": "assistant", "content": "</think>\n{"})
    if system_prompt:
        messages.insert(0, {"role": "system", "content": system_prompt})
    return messages


def call_local_llm(prompt: str, system_prompt: str | None = None, model: str | None = None) -> str:
    url = f"{_local_llm_base_url()}/chat/completions"
    selected_model = model or _local_llm_model()
    messages = build_local_messages(prompt, system_prompt, selected_model)

    payload = {
        "model": selected_model,
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": 512,
        "cache_prompt": False,
    }

    # LM Studio's local model can reuse a generation slot across concurrent
    # requests even when prompt caching is disabled. Serialize calls so one
    # job cannot receive another job's completion.
    with _LOCAL_LLM_LOCK:
        resp = httpx.post(url, json=payload, timeout=_local_llm_timeout())
    resp.raise_for_status()
    data = resp.json()
    response_model = data.get("model", "unknown")
    logger.info("Local LLM response model: %s", response_model)
    if response_model != "unknown" and response_model != selected_model:
        raise RuntimeError(
            f"Local LLM returned {response_model!r} instead of requested {selected_model!r}"
        )
    raw_content = data["choices"][0]["message"]["content"] or ""
    return parse_prefilled_completion(raw_content)


def call_anthropic(prompt: str, system_prompt: str | None = None) -> str:
    from anthropic import Anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    client = Anthropic(api_key=api_key)
    messages = [{"role": "user", "content": prompt}]
    if system_prompt:
        messages = [{"role": "user", "content": prompt}]

    response = client.messages.create(
        model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        max_tokens=int(os.getenv("ANTHROPIC_MAX_TOKENS", "600")),
        system=system_prompt,
        messages=messages,
    )
    return response.content[0].text.strip()


def generate_text(prompt: str, system_prompt: str | None = None, model: str | None = None) -> str:
    provider = os.getenv("LLM_PROVIDER", "local").lower()
    prompt_chars = len(prompt) + len(system_prompt or "")
    start = time.monotonic()

    def _log_timing(used_provider: str):
        elapsed = time.monotonic() - start
        logger.info(
            f"LLM call [{used_provider}]: {elapsed:.2f}s, prompt={prompt_chars} chars"
        )

    if provider == "anthropic":
        try:
            result = call_anthropic(prompt, system_prompt)
            _log_timing("anthropic")
            return result
        except Exception as exc:
            logger.warning("Anthropic provider failed: %s", exc)

    if provider in {"local", "openai_compatible"}:
        try:
            result = call_local_llm(prompt, system_prompt, model)
            _log_timing(f"local:{model or _local_llm_model()}")
            return result
        except Exception as exc:
            logger.warning("Local LLM provider failed: %s", exc)

    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            result = call_anthropic(prompt, system_prompt)
            _log_timing("anthropic_fallback")
            return result
        except Exception as exc:
            logger.warning("Anthropic fallback failed: %s", exc)

    raise RuntimeError(
        "No LLM provider available. Set LLM_PROVIDER=local with LOCAL_LLM_BASE_URL and LOCAL_LLM_MODEL or configure ANTHROPIC_API_KEY."
    )
