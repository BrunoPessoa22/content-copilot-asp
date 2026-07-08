"""Voice profile loader — pins output to an author's DNA.

Profiles ship as YAML files under ``profiles/``. A profile is a natural-language
DNA summary the LLM reads, plus a banned-words list and a preferred-words list.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

PROFILE_DIR = Path(__file__).parent.parent / "profiles"


DEFAULT_PROFILES: dict[str, dict[str, Any]] = {
    "generic-founder": {
        "name": "generic-founder",
        "dna_summary": (
            "Direct, opinionated, first-person. Casual but competent. Short sentences. "
            "Concrete numbers over vague adjectives. Real experience over abstract advice. "
            "Never corporate. Never overexplained. Reads like a text from a friend who "
            "happens to know the domain."
        ),
        "banned": ["synergy", "leverage", "ecosystem", "seamless", "world-class"],
        "preferred": ["real", "concrete", "shipped", "built"],
    },
    "bruno-pt-br": {
        "name": "bruno-pt-br",
        "dna_summary": (
            "Brazilian Portuguese, casual: 'voce', 'beleza', 'bora', 'valeu', 'top', "
            "'show', 'massa', 'cara'. Direct. One-sentence takes, not paragraphs. "
            "Opinionated. Uses specific numbers ('8K members', not 'large community'). "
            "References real past experience casually. Never defensive, never apologetic. "
            "Hates corporate jargon. Loves speed and clarity."
        ),
        "banned": [
            "sinergia", "alavancar", "disruptivo", "holistico", "at the end of the day",
            "no final do dia", "vale ressaltar", "em suma",
        ],
        "preferred": ["na pratica", "de verdade", "bora", "faz sentido", "sem enrolacao"],
    },
}


def load_voice_profile(name: str) -> dict[str, Any]:
    """Load a profile by name. Falls back to generic-founder if unknown."""
    profile_path = PROFILE_DIR / f"{name}.json"
    if profile_path.exists():
        import json
        return json.loads(profile_path.read_text())
    return DEFAULT_PROFILES.get(name, DEFAULT_PROFILES["generic-founder"])
