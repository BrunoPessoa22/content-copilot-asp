"""LLM access — dispatch-first, Anthropic API fallback.

Two backends, tried in order:

1. ``LLM_DISPATCH_URL`` — a private completion endpoint (Claude subscription,
   no metered credits). POST /complete {prompt, system?, model?} with a bearer.
2. ``ANTHROPIC_API_KEY`` — the metered Anthropic API via the official SDK.

Callers pick a tier, not a model: "fast" for scoring passes, "quality" for
final copy generation. Model ids are env-overridable.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger("content_copilot.llm")

MODEL_FAST = os.environ.get("CC_MODEL_FAST", "claude-haiku-4-5-20251001")
MODEL_QUALITY = os.environ.get("CC_MODEL_QUALITY", "claude-sonnet-5")


class LlmUnavailable(RuntimeError):
    """Neither LLM backend is configured/reachable."""


def _model_for(tier: str) -> str:
    return MODEL_QUALITY if tier == "quality" else MODEL_FAST


async def _via_dispatch(prompt: str, system: str | None, model: str) -> str | None:
    url = os.environ.get("LLM_DISPATCH_URL", "").rstrip("/")
    secret = os.environ.get("LLM_DISPATCH_SECRET", "")
    if not url or not secret:
        return None
    payload: dict = {"prompt": prompt, "model": model}
    if system:
        payload["system"] = system
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            r = await client.post(
                f"{url}/complete",
                json=payload,
                headers={"Authorization": f"Bearer {secret}"},
            )
            r.raise_for_status()
            text = r.json().get("text", "")
            return text or None
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("llm_dispatch_failed model=%s err=%s", model, exc)
        return None


async def _via_anthropic(prompt: str, system: str | None, model: str, max_tokens: int) -> str | None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic

        client = anthropic.AsyncAnthropic()
        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        resp = await client.messages.create(**kwargs)
        return resp.content[0].text
    except Exception as exc:  # noqa: BLE001 - any SDK/API failure falls through to the caller
        logger.warning("anthropic_api_failed model=%s err=%s", model, exc)
        return None


async def complete(
    prompt: str,
    *,
    tier: str = "fast",
    system: str | None = None,
    max_tokens: int = 4096,
) -> str:
    """Run a completion on the configured backend. Raises LlmUnavailable if none works."""
    model = _model_for(tier)
    text = await _via_dispatch(prompt, system, model)
    if text is None:
        text = await _via_anthropic(prompt, system, model, max_tokens)
    if text is None:
        raise LlmUnavailable(
            "no LLM backend available (set LLM_DISPATCH_URL+LLM_DISPATCH_SECRET "
            "or ANTHROPIC_API_KEY)"
        )
    return text


def extract_json(text: str, opener: str = "{", closer: str = "}"):
    """Pull the first JSON value out of an LLM reply (tolerates prose around it)."""
    import json

    start = text.find(opener)
    end = text.rfind(closer)
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"no JSON {opener}...{closer} found in LLM reply")
    return json.loads(text[start : end + 1])
