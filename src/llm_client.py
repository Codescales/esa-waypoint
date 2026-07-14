"""Thin OpenAI-compatible LLM client.

Usage::

    from src.llm_client import complete

    prose = complete(system="You are a brief writer.", user="Write a brief for...")

Environment variables (see web/backend/config.py):
    LLM_BASE_URL        Base URL for the OpenAI-compatible gateway (required unless LLM_DISABLED)
    LLM_API_KEY         API key (required unless LLM_DISABLED)
    LLM_MODEL           Model name (default: gpt-4o)
    LLM_DISABLED        Set to "1" / "true" to skip the LLM and return the fallback string

When LLM_DISABLED is set, complete() returns the ``disabled_fallback`` argument unchanged
(defaults to empty string). This keeps tests and offline runs deterministic.
"""

import os
import time
from typing import Optional

import httpx

_BASE_URL = os.environ.get("LLM_BASE_URL", "")
_API_KEY = os.environ.get("LLM_API_KEY", "")
_MODEL = os.environ.get("LLM_MODEL", "gpt-4o")
_DISABLED = os.environ.get("LLM_DISABLED", "").lower() in ("1", "true", "yes")
_VERIFY_SSL = os.environ.get("LLM_VERIFY_SSL", "true").lower() in ("1", "true", "yes")

_MAX_RETRIES = 3
_RETRY_DELAYS = [2, 5, 10]  # seconds between attempts


def complete(
    system: str,
    user: str,
    *,
    model: Optional[str] = None,
    disabled_fallback: str = "",
) -> str:
    """Call the LLM and return the response text.

    Args:
        system: System prompt.
        user: User message / brief-authoring prompt.
        model: Override the model for this call (default: LLM_MODEL env var).
        disabled_fallback: Returned as-is when LLM_DISABLED=1.

    Returns:
        The assistant's text response.

    Raises:
        RuntimeError: If LLM_BASE_URL or LLM_API_KEY is missing and LLM_DISABLED is not set.
        Exception: Propagated after all retries are exhausted.
    """
    if _DISABLED:
        return disabled_fallback

    base_url = _BASE_URL or os.environ.get("LLM_BASE_URL", "")
    api_key = _API_KEY or os.environ.get("LLM_API_KEY", "")

    if not base_url:
        raise RuntimeError(
            "LLM_BASE_URL is not set. Set it to your OpenAI-compatible gateway URL, "
            "or set LLM_DISABLED=1 to skip LLM calls."
        )
    if not api_key:
        raise RuntimeError(
            "LLM_API_KEY is not set. Provide an API key for the gateway, "
            "or set LLM_DISABLED=1 to skip LLM calls."
        )

    resolved_model = model or _MODEL or os.environ.get("LLM_MODEL", "gpt-4o")

    try:
        from openai import OpenAI, APIError, APITimeoutError, RateLimitError
    except ImportError as exc:
        raise RuntimeError(
            "openai package is not installed. Run: pip install openai"
        ) from exc

    client = OpenAI(base_url=base_url, api_key=api_key, http_client=httpx.Client(verify=_VERIFY_SSL))

    last_exc: Optional[Exception] = None
    for attempt, delay in enumerate([0] + _RETRY_DELAYS, start=1):
        if delay:
            time.sleep(delay)
        try:
            response = client.chat.completions.create(
                model=resolved_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                timeout=120,
            )
            return response.choices[0].message.content or ""
        except (RateLimitError, APITimeoutError) as exc:
            last_exc = exc
            continue
        except APIError as exc:
            # Non-retryable (4xx other than 429)
            raise
        except Exception as exc:
            last_exc = exc
            continue

    raise RuntimeError(
        f"LLM call failed after {_MAX_RETRIES + 1} attempts: {last_exc}"
    ) from last_exc
