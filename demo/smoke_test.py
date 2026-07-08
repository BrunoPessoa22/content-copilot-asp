"""Offline smoke test — proves the pipeline wires end-to-end without yt-dlp/Whisper.

Runs ingest (pre-seeded transcript), mine_moments (real LLM call), pack (real
LLM call). Exits non-zero on any failure. Used for pre-demo verification.

Needs one LLM backend: LLM_DISPATCH_URL+LLM_DISPATCH_SECRET or ANTHROPIC_API_KEY.

Usage:
    python demo/smoke_test.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("CC_SESSION_DIR", "/tmp/content-copilot-smoke")

from src import ingest, mine, pack  # noqa: E402
from src.voice_dna import load_voice_profile  # noqa: E402


STUB_TRANSCRIPT = {
    "segments": [
        {"start": 0.0, "end": 6.5, "text": "Escalei uma escola de programacao para 33 franquias em cinco anos."},
        {"start": 6.5, "end": 14.2, "text": "Achei que sabia o que era escala. Nao sabia nada."},
        {"start": 14.2, "end": 22.8, "text": "Hoje rodo vinte agentes de IA vinte e quatro horas por dia."},
        {"start": 22.8, "end": 31.0, "text": "Escala de verdade e quando voce dorme e o trabalho continua acontecendo."},
        {"start": 31.0, "end": 40.5, "text": "O futuro do trabalho nao e substituir pessoas. E dar superpoderes pra quem ja e bom."},
    ]
}


async def main() -> int:
    fake_url = "https://smoke.local/scale-episode.mp3"
    sid = ingest._session_id(fake_url)
    stub_dir = Path(os.environ["CC_SESSION_DIR"]) / sid
    stub_dir.mkdir(parents=True, exist_ok=True)
    (stub_dir / "transcript.json").write_text(json.dumps(STUB_TRANSCRIPT, ensure_ascii=False))
    (stub_dir / "manifest.json").write_text(json.dumps({
        "session_id": sid,
        "source_url": fake_url,
        "kind": "audio",
        "transcription": "stub",
        "segments": len(STUB_TRANSCRIPT["segments"]),
        "duration_s": STUB_TRANSCRIPT["segments"][-1]["end"],
        "cached": False,
    }))

    print("=== 1. ingest (pre-seeded session; cache-hit path) ===")
    ingested = await ingest.run(fake_url)
    print(json.dumps(ingested, indent=2, ensure_ascii=False))
    assert ingested["session_id"] == sid, "session_id mismatch"
    assert ingested["cached"] is True, "expected the cached manifest"

    print("\n=== 2. mine_moments (real LLM) ===")
    mined = await mine.run(sid, top_k=3)
    print(json.dumps(mined, indent=2, ensure_ascii=False))
    assert mined["moments"], "expected at least one moment"

    top = mined["moments"][0]
    print(f"\n=== 3. pack(target=x, voice=bruno-pt-br) [moment {top['moment_id']} conf={top['confidence']}] ===")
    voice = load_voice_profile("bruno-pt-br")
    packed = await pack.run(sid, top["moment_id"], "x", voice)
    print(json.dumps(packed, indent=2, ensure_ascii=False))
    assert packed["body"], "pack returned empty body"

    print("\nSMOKE OK — pipeline end-to-end verified.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
