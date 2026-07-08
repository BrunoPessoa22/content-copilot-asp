"""Best-effort operational alerting via a webhook (Slack-compatible).

Fires on the things the app can detect itself: settlement failures, boot/handshake
failures, and upstream-down. "Gateway is down" must be detected externally (an
uptime monitor hitting /health) — a dead process can't alert.

No-ops cleanly if ALERT_WEBHOOK_URL is unset, and never raises into the caller.
"""

import json
import logging

import httpx

from .config import settings

logger = logging.getLogger("content_copilot_gateway.alerts")


async def alert(event: str, **fields: object) -> None:
    """Post an alert to the configured webhook. Never raises."""
    payload = {"event": event, **fields}
    logger.warning(json.dumps({"alert": payload}, default=str))
    url = settings.alert_webhook_url
    if not url:
        return
    text = f":rotating_light: *Content Copilot gateway* — {event}\n```{json.dumps(fields, default=str)[:1500]}```"
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            await c.post(url, json={"text": text})
    except httpx.HTTPError as exc:  # never let alerting break the request path
        logger.error("alert_webhook_failed: %s", exc)
