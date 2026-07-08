"""End-to-end demo call — used in the 90s X post video.

Runs one full pipeline: ingest -> mine -> pack (x) -> ship (stub).
Prints each step's output as JSON so it screencaps cleanly for the demo video.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import ingest, mine, pack
from src.voice_dna import load_voice_profile


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("source_url")
    p.add_argument("--voice", default="bruno-pt-br")
    p.add_argument("--target", default="x", choices=["x", "linkedin", "ig_reel", "newsletter"])
    args = p.parse_args()

    print("=== 1. ingest ===")
    m = await ingest.run(args.source_url)
    print(json.dumps(m, indent=2, ensure_ascii=False))

    print("\n=== 2. mine_moments ===")
    r = await mine.run(m["session_id"], top_k=3)
    print(json.dumps(r, indent=2, ensure_ascii=False))

    if not r["moments"]:
        print("no moments — exiting")
        return

    print(f"\n=== 3. pack(target={args.target}) ===")
    voice = load_voice_profile(args.voice)
    pk = await pack.run(m["session_id"], r["moments"][0]["moment_id"], args.target, voice)
    print(json.dumps(pk, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
