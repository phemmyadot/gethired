import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def _local_llm_base_url() -> str:
    return os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1").rstrip("/")


def _local_llm_model() -> str:
    return os.getenv("LOCAL_LLM_MODEL", "llama3.1")


def _local_llm_timeout() -> float:
    return float(os.getenv("LOCAL_LLM_TIMEOUT", "120"))


def call_local_llm(prompt: str, system_prompt: str | None = None) -> str:
    url = f"{_local_llm_base_url()}/chat/completions"
    messages: list[dict[str, str]] = [{"role": "user", "content": prompt}]
    if system_prompt:
        messages.insert(0, {"role": "system", "content": system_prompt})

    payload = {
        "model": _local_llm_model(),
        "messages": messages,
        "temperature": 0.2,
    }

    resp = httpx.post(url, json=payload, timeout=_local_llm_timeout())
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


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


def generate_text(prompt: str, system_prompt: str | None = None) -> str:
    provider = os.getenv("LLM_PROVIDER", "local").lower()

    if provider == "anthropic":
        try:
            return call_anthropic(prompt, system_prompt)
        except Exception as exc:
            logger.warning("Anthropic provider failed: %s", exc)

    if provider in {"local", "openai_compatible"}:
        try:
            return call_local_llm(prompt, system_prompt)
        except Exception as exc:
            logger.warning("Local LLM provider failed: %s", exc)

    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            return call_anthropic(prompt, system_prompt)
        except Exception as exc:
            logger.warning("Anthropic fallback failed: %s", exc)

    raise RuntimeError(
        "No LLM provider available. Set LLM_PROVIDER=local with LOCAL_LLM_BASE_URL and LOCAL_LLM_MODEL or configure ANTHROPIC_API_KEY."
    )
