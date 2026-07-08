"""Channel-native content pack generation.

Each target has hard-coded channel rules (character limits, hook shape,
subtitle position math, banned-word lists) that were learned from the
Bruno Pessoa content fleet in production.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import anthropic

SESSION_DIR = Path(os.environ.get("CC_SESSION_DIR", "/tmp/content-copilot"))


CHANNEL_RULES = {
    "x": {
        "char_ceiling": 280,
        "thread_ceiling": 6,
        "hook_rules": "Open with a concrete number, name, or stake. Never with 'Tem gente que acha' or 'A lot of people think'. First-person is fine only if the speaker is the author.",
        "banned": ["synergy", "leverage", "ecosystem", "unlock", "empower", "cutting-edge", "seamless", "robust", "at the end of the day"],
    },
    "linkedin": {
        "char_ceiling": 3000,
        "hook_rules": "First 3 lines must earn the click-more expand. Open with a moment or number.",
        "banned": ["synergy", "leverage", "paradigm shift", "world-class"],
    },
    "ig_reel": {
        "duration_max_s": 40,
        "subtitle_rules": "FontSize 12 Bold 0 Alignment 2 MarginV 280-320 for 1080x1920. Never top. Never large. Regenerate ASS whenever cut spec changes.",
        "hook_rules": "First-person stake in first 8s. Never generic self-reflection. Speaker-verify: crop the actual speaker, panorama letterbox as fallback.",
    },
    "newsletter": {
        "char_ceiling": 600,
        "hook_rules": "One-line hook + one-paragraph story + one-line takeaway. No 'In today's landscape'.",
    },
}


TEMPLATES = {
    "x": """You write in this voice profile — obey it strictly:
{voice}

Turn this quote into either (a) a single tweet under 280 chars, or (b) a thread of 3-6 tweets if the substance warrants it. Rules: {rules}. Return JSON: {{"kind": "single|thread", "tweets": ["...", "..."]}}. Quote:
{quote}""",
    "linkedin": """Voice profile — obey strictly:
{voice}

Turn this quote into a LinkedIn long-form post (under 3000 chars). Rules: {rules}. Return JSON: {{"body": "..."}}. Quote:
{quote}""",
    "ig_reel": """Voice profile — obey strictly:
{voice}

The source has a moment from {start:.1f}s to {end:.1f}s. Design an IG Reel: hook line (spoken in ≤8s), full script pinned to the quote, ffmpeg cut spec, and ASS subtitle lines. Rules: {rules}. Return JSON: {{"hook": "...", "script": "...", "ffmpeg_cmd": "...", "ass_subtitles": ["..."]}}. Quote:
{quote}""",
    "newsletter": """Voice profile — obey strictly:
{voice}

Turn this quote into a newsletter blurb under 600 chars. Rules: {rules}. Return JSON: {{"blurb": "...", "cta": "..."}}. Quote:
{quote}""",
}


async def run(session_id: str, moment_id: str, target: str, voice: dict[str, Any]) -> dict[str, Any]:
    if target not in CHANNEL_RULES:
        raise ValueError(f"unknown target: {target}")
    session_dir = SESSION_DIR / session_id
    moments = json.loads((session_dir / "moments.json").read_text())
    moment = next((m for m in moments if m["moment_id"] == moment_id), None)
    if not moment:
        raise ValueError(f"unknown moment_id: {moment_id}")

    rules = CHANNEL_RULES[target]
    prompt = TEMPLATES[target].format(
        voice=voice["dna_summary"],
        rules=json.dumps(rules, ensure_ascii=False),
        quote=moment["quote"],
        start=moment["start_s"],
        end=moment["end_s"],
    )
    client = anthropic.AsyncAnthropic()
    resp = await client.messages.create(
        model=os.environ.get("CC_PACK_MODEL", "claude-sonnet-4-6"),
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text
    start, end = text.find("{"), text.rfind("}")
    body = json.loads(text[start : end + 1])

    pack_id = f"p_{moment_id}_{target}"
    pack_out = {
        "pack_id": pack_id,
        "session_id": session_id,
        "moment_id": moment_id,
        "target": target,
        "voice_profile": voice["name"],
        "body": body,
        "moment": moment,
    }
    packs_dir = session_dir / "packs"
    packs_dir.mkdir(exist_ok=True)
    (packs_dir / f"{pack_id}.json").write_text(json.dumps(pack_out, ensure_ascii=False))
    return pack_out
