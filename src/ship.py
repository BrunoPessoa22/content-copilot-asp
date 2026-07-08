"""Publish adapters — Typefully, Instagram Graph, LinkedIn, Resend.

``credentials_ref`` is a caller-owned reference (e.g. a keychain URI or the
caller-agent's own secret alias). The ASP never stores caller credentials —
it fetches them via the reference at call time and drops them after.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import httpx

SESSION_DIR = Path(os.environ.get("CC_SESSION_DIR", "/tmp/content-copilot"))


class ShipError(RuntimeError):
    """Pack missing, credential ref unknown, or downstream rejected the publish."""


def _resolve_credential(ref: str) -> dict[str, str]:
    """Resolve a server-registered credential reference.

    v1 supports refs pre-registered with the operator (env vars prefixed with
    the upper-cased ref name, e.g. ref ``demo-x`` -> ``DEMO_X_TYPEFULLY_API_KEY``).
    Caller credentials are never persisted per-call. An unknown ref fails the
    call BEFORE any publish attempt (and, behind the paywall, before billing).
    """
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", ref):
        raise ShipError(f"invalid credentials_ref: {ref!r}")
    prefix = ref.upper().replace("-", "_") + "_"
    creds = {k[len(prefix):]: v for k, v in os.environ.items() if k.startswith(prefix)}
    if not creds:
        raise ShipError(
            f"unknown credentials_ref {ref!r} — register a downstream credential "
            "with the operator first (see /terms)"
        )
    return creds


async def _ship_x(pack: dict[str, Any], creds: dict[str, str]) -> dict[str, Any]:
    """Publish via Typefully — schedule=now for immediate."""
    tweets = pack["body"].get("tweets", [pack["body"].get("body", "")])
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            "https://api.typefully.com/v1/drafts/",
            headers={"X-API-KEY": creds["TYPEFULLY_API_KEY"], "Content-Type": "application/json"},
            json={"content": "\n\n".join(tweets), "schedule-date": "now"},
        )
        r.raise_for_status()
        data = r.json()
        return {"provider": "typefully", "id": data.get("id"), "share_url": data.get("share_url")}


async def _ship_linkedin(pack: dict[str, Any], creds: dict[str, str]) -> dict[str, Any]:
    body = pack["body"]["body"]
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            "https://api.linkedin.com/v2/ugcPosts",
            headers={
                "Authorization": f"Bearer {creds['LI_ACCESS_TOKEN']}",
                "X-Restli-Protocol-Version": "2.0.0",
                "Content-Type": "application/json",
            },
            json={
                "author": f"urn:li:person:{creds['LI_PERSON_URN']}",
                "lifecycleState": "PUBLISHED",
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {"text": body},
                        "shareMediaCategory": "NONE",
                    }
                },
                "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
            },
        )
        r.raise_for_status()
        return {"provider": "linkedin", "id": r.headers.get("x-restli-id")}


async def _ship_ig_reel(pack: dict[str, Any], creds: dict[str, str]) -> dict[str, Any]:
    return {"provider": "instagram", "note": "reel publish requires video_url from ffmpeg_cmd render step"}


async def _ship_newsletter(pack: dict[str, Any], creds: dict[str, str]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {creds['RESEND_API_KEY']}", "Content-Type": "application/json"},
            json={
                "from": creds.get("RESEND_FROM", "hello@example.com"),
                "to": creds["RESEND_TO"].split(","),
                "subject": pack["body"].get("subject", "New from Content Copilot"),
                "text": pack["body"]["blurb"] + "\n\n" + pack["body"]["cta"],
            },
        )
        r.raise_for_status()
        return {"provider": "resend", "id": r.json().get("id")}


async def run(session_id: str, pack_id: str, credentials_ref: str) -> dict[str, Any]:
    pack_path = SESSION_DIR / session_id / "packs" / f"{pack_id}.json"
    if not pack_path.exists():
        raise ShipError(f"unknown pack_id {pack_id!r} for session {session_id!r} — call pack first")
    pack = json.loads(pack_path.read_text())
    creds = _resolve_credential(credentials_ref)
    target = pack["target"]
    dispatch = {
        "x": _ship_x,
        "linkedin": _ship_linkedin,
        "ig_reel": _ship_ig_reel,
        "newsletter": _ship_newsletter,
    }
    try:
        return await dispatch[target](pack, creds)
    except KeyError as exc:
        raise ShipError(f"credential ref {credentials_ref!r} is missing key {exc} for target {target!r}")
    except httpx.HTTPStatusError as exc:
        raise ShipError(
            f"downstream {target} rejected the publish: HTTP {exc.response.status_code}"
        )
    except httpx.HTTPError as exc:
        raise ShipError(f"downstream {target} unreachable: {exc}")
