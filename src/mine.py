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
import logging
import os
from pathlib import Path
from typing import Any

from . import llm

logger = logging.getLogger("content_copilot.mine")

SESSION_DIR = Path(os.environ.get("CC_SESSION_DIR", "/tmp/content-copilot"))

DEFAULT_WEIGHTS = {
    "novelty": 0.28, "tension": 0.22, "stakes": 0.20, "quote": 0.18, "hookability": 0.12,
}

# Cap how many candidate windows go to the scoring model in one pass. A 3-hour
# source can produce 400+ windows; scoring them all costs more than the call
# earns. Windows are sampled evenly across the source when over the cap.
MAX_WINDOWS = int(os.environ.get("CC_MAX_SCORE_WINDOWS", "120"))

SCORING_PROMPT = """You score podcast/interview segments for shareability. Score each dimension 0.0-1.0:
- novelty: how different from stock advice/platitudes (0=cliche, 1=genuinely new)
- tension: names a real conflict, tradeoff, or contradiction (0=none, 1=sharp)
- stakes: names a concrete consequence (0=abstract, 1=named + costed)
- quote: contains a verbatim line worth pulling (0=none, 1=shareworthy quote)
- hookability: first 8s stands alone as a hook (0=needs setup, 1=cold-open ready)

Return strict JSON: [{"segment_idx": N, "novelty": F, "tension": F, "stakes": F, "quote": F, "hookability": F, "quote_text": "..."}...]
"""


class MineError(RuntimeError):
    """Session missing or transcript unusable."""


def _slide_segments(
    transcript: dict[str, Any], min_s: float = 10.0, max_s: float = 40.0
) -> list[dict[str, Any]]:
    """Group transcript segments into 10-40s candidate windows on sentence boundaries."""
    segs = transcript.get("segments", [])
    windows: list[dict[str, Any]] = []
    cur: dict[str, Any] = {"start": None, "end": None, "text": ""}
    for s in segs:
        if cur["start"] is None:
            cur["start"] = s["start"]
        cur["text"] = (cur["text"] + " " + s["text"]).strip()
        cur["end"] = s["end"]
        dur = cur["end"] - cur["start"]
        if dur >= min_s and (s["text"].rstrip().endswith((".", "?", "!")) or dur >= max_s):
            windows.append(cur)
            cur = {"start": None, "end": None, "text": ""}
    if cur["start"] is not None and (cur["end"] - cur["start"]) >= min_s:
        windows.append(cur)
    return windows


def _sample_evenly(windows: list[dict[str, Any]], cap: int) -> list[tuple[int, dict[str, Any]]]:
    indexed = list(enumerate(windows))
    if len(indexed) <= cap:
        return indexed
    step = len(indexed) / cap
    return [indexed[int(i * step)] for i in range(cap)]


def _clamp(v: Any) -> float:
    try:
        return min(1.0, max(0.0, float(v)))
    except (TypeError, ValueError):
        return 0.0


async def run(
    session_id: str, top_k: int = 10, weights: dict[str, float] | None = None
) -> dict[str, Any]:
    weights = weights or DEFAULT_WEIGHTS
    top_k = min(40, max(1, int(top_k)))
    session_dir = SESSION_DIR / session_id
    transcript_path = session_dir / "transcript.json"
    if not transcript_path.exists():
        raise MineError(f"no transcript for {session_id} — call ingest first")

    transcript = json.loads(transcript_path.read_text())
    windows = _slide_segments(transcript)
    if not windows:
        return {"session_id": session_id, "moments": []}

    sampled = _sample_evenly(windows, MAX_WINDOWS)
    batch_prompt = SCORING_PROMPT + "\n\n" + json.dumps(
        [{"idx": i, "text": w["text"]} for i, w in sampled], ensure_ascii=False
    )
    text = await llm.complete(batch_prompt, tier="fast")
    try:
        scores = llm.extract_json(text, "[", "]")
    except (ValueError, json.JSONDecodeError) as exc:
        raise MineError(f"scoring pass returned unparseable output: {exc}")

    valid_idx = {i for i, _ in sampled}
    ranked: list[dict[str, Any]] = []
    for s in scores:
        if not isinstance(s, dict):
            continue
        idx = s.get("segment_idx")
        if idx not in valid_idx:
            continue
        dims = {k: _clamp(s.get(k)) for k in weights}
        conf = sum(dims[k] * weights[k] for k in weights) * 100
        w = windows[idx]
        ranked.append({
            "moment_id": f"m_{session_id}_{idx:03d}",
            "start_s": w["start"],
            "end_s": w["end"],
            "duration_s": round(w["end"] - w["start"], 2),
            "confidence": round(conf, 1),
            "quote": (s.get("quote_text") or w["text"][:200]).strip(),
            "scores": dims,
        })
    ranked.sort(key=lambda x: x["confidence"], reverse=True)
    top = ranked[:top_k]

    (session_dir / "moments.json").write_text(json.dumps(top, ensure_ascii=False))
    return {"session_id": session_id, "moments": top}
