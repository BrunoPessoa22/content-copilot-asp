"""Moment mining — rank 10-40s segments by content value.

Scoring dimensions (each 0-1, weighted-summed to a 0-100 confidence):
- **novelty**   — how different is this from platitudes / stock quotes
- **tension**   — does it name a real conflict, tradeoff, or stake
- **stakes**    — is a concrete consequence named
- **quote**     — is there a verbatim line worth pulling
- **hookability** — first 8s of the segment stands on its own

Weights are learned from rejection-log feedback (Falcao fleet, ~1200 labelled
segments). Weights ship pre-trained; callers can override with `weights` param.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import anthropic

SESSION_DIR = Path(os.environ.get("CC_SESSION_DIR", "/tmp/content-copilot"))

DEFAULT_WEIGHTS = {"novelty": 0.28, "tension": 0.22, "stakes": 0.20, "quote": 0.18, "hookability": 0.12}

SCORING_PROMPT = """You score podcast/interview segments for shareability. Score each dimension 0.0-1.0:
- novelty: how different from stock advice/platitudes (0=cliche, 1=genuinely new)
- tension: names a real conflict, tradeoff, or contradiction (0=none, 1=sharp)
- stakes: names a concrete consequence (0=abstract, 1=named + costed)
- quote: contains a verbatim line worth pulling (0=none, 1=shareworthy quote)
- hookability: first 8s stands alone as a hook (0=needs setup, 1=cold-open ready)

Return strict JSON: [{"segment_idx": N, "novelty": F, "tension": F, "stakes": F, "quote": F, "hookability": F, "quote_text": "..."}...]
"""


def _slide_segments(transcript: dict[str, Any], min_s: float = 10.0, max_s: float = 40.0) -> list[dict[str, Any]]:
    """Group whisper word-timestamps into 10-40s candidate segments on sentence boundaries."""
    segs = transcript.get("segments", [])
    windows = []
    cur = {"start": None, "end": None, "text": ""}
    for s in segs:
        if cur["start"] is None:
            cur["start"] = s["start"]
        cur["text"] += (" " + s["text"]).strip()
        cur["end"] = s["end"]
        dur = cur["end"] - cur["start"]
        if dur >= min_s and (s["text"].rstrip().endswith((".", "?", "!")) or dur >= max_s):
            windows.append(cur)
            cur = {"start": None, "end": None, "text": ""}
    if cur["start"] is not None and (cur["end"] - cur["start"]) >= min_s:
        windows.append(cur)
    return windows


async def run(session_id: str, top_k: int = 10, weights: dict[str, float] | None = None) -> dict[str, Any]:
    weights = weights or DEFAULT_WEIGHTS
    session_dir = SESSION_DIR / session_id
    transcript_path = next(session_dir.glob("*.json"), None) if session_dir.exists() else None
    if not transcript_path:
        raise FileNotFoundError(f"no transcript for {session_id} — call ingest first")

    transcript = json.loads(transcript_path.read_text())
    windows = _slide_segments(transcript)
    if not windows:
        return {"session_id": session_id, "moments": []}

    client = anthropic.AsyncAnthropic()
    batch_prompt = SCORING_PROMPT + "\n\n" + json.dumps(
        [{"idx": i, "text": w["text"]} for i, w in enumerate(windows)]
    )
    resp = await client.messages.create(
        model=os.environ.get("CC_SCORING_MODEL", "claude-haiku-4-5-20251001"),
        max_tokens=4096,
        messages=[{"role": "user", "content": batch_prompt}],
    )
    text = resp.content[0].text
    start, end = text.find("["), text.rfind("]")
    scores = json.loads(text[start : end + 1])

    ranked = []
    for s in scores:
        idx = s["segment_idx"]
        conf = sum(s[k] * weights[k] for k in weights) * 100
        w = windows[idx]
        ranked.append({
            "moment_id": f"m_{session_id}_{idx:03d}",
            "start_s": w["start"],
            "end_s": w["end"],
            "duration_s": round(w["end"] - w["start"], 2),
            "confidence": round(conf, 1),
            "quote": s.get("quote_text", w["text"][:200]),
            "scores": {k: s[k] for k in weights},
        })
    ranked.sort(key=lambda x: x["confidence"], reverse=True)
    top = ranked[:top_k]

    (session_dir / "moments.json").write_text(json.dumps(top))
    return {"session_id": session_id, "moments": top}
