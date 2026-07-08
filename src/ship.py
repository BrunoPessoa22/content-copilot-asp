"""Publish adapters — Typefully, Instagram Graph, LinkedIn, Resend.

``credentials_ref`` is a caller-owned reference (e.g. a keychain URI or the
caller-agent's own secret alias). The ASP never stores caller credentials —
it fetches them via the reference at call time and drops them after.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

SESSION_DIR = Path(os.environ.get("CC_SESSION_DIR", "/tmp/content-copilot"))


def _resolve_credential(ref: str) -> dict[str, str]:
    """Placeholder for the caller credential resolver.

    Real impl reads from the caller-agent's secret store using the ref. For
    local dev, resolve via env vars keyed by the ref name.
    """
    prefix = ref.upper().replace("-", "_") + "_"
    return {k[len(prefix):]: v for k, v in os.environ.items() if k.startswith(prefix)}


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
    packs_dir = SESSION_DIR / session_id / "packs"
    pack = json.loads((packs_dir / f"{pack_id}.json").read_text())
    creds = _resolve_credential(credentials_ref)
    target = pack["target"]
    dispatch = {
        "x": _ship_x,
        "linkedin": _ship_linkedin,
        "ig_reel": _ship_ig_reel,
        "newsletter": _ship_newsletter,
    }
    return await dispatch[target](pack, creds)
