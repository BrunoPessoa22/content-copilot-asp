"""Content Copilot MCP server (local / stdio).

Exposes the four verbs — ingest, mine_moments, pack, ship — as MCP tools for
LOCAL agent use (Claude Code, OpenClaw, any MCP client). This mode is unmetered:
it runs the pipeline directly with the operator's own credentials.

The PAID surface for the OKX.AI marketplace is ``app.main`` — a FastAPI server
where every verb sits behind an x402 payment wall (HTTP 402 challenge, EIP-3009
signature, on-chain USDT0 settlement on X Layer via the OKX Broker).

Run:  python -m src.server
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from . import ingest, mine, pack, ship
from .voice_dna import load_voice_profile

server = Server("content-copilot")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="content_copilot.ingest",
            description=(
                "Download and transcribe a raw source (YouTube, podcast RSS episode, "
                "MP3/MP4 URL, article). Returns a session_id used by every downstream verb."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "source_url": {"type": "string"},
                    "kind": {
                        "type": "string",
                        "enum": ["auto", "youtube", "podcast", "audio", "video", "article"],
                        "default": "auto",
                    },
                },
                "required": ["source_url"],
            },
        ),
        Tool(
            name="content_copilot.mine_moments",
            description=(
                "Rank 10-40s segments of an ingested source by novelty, tension, stakes, "
                "and quote-density. Returns the top-k with verbatim quotes and confidence."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "top_k": {"type": "integer", "default": 10, "minimum": 1, "maximum": 40},
                },
                "required": ["session_id"],
            },
        ),
        Tool(
            name="content_copilot.pack",
            description=(
                "Generate a channel-native content pack from one mined moment. Targets: "
                "'x' (tweet or thread), 'linkedin' (long-form post), 'ig_reel' (ffmpeg cut "
                "spec + ASS subtitles + hook), 'newsletter' (blurb + CTA). Optional "
                "voice_profile pins the output to a specific author's voice DNA."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "moment_id": {"type": "string"},
                    "target": {
                        "type": "string",
                        "enum": ["x", "linkedin", "ig_reel", "newsletter"],
                    },
                    "voice_profile": {"type": "string", "default": "generic-founder"},
                },
                "required": ["session_id", "moment_id", "target"],
            },
        ),
        Tool(
            name="content_copilot.ship",
            description=(
                "Publish a pack through a server-registered downstream credential "
                "(Typefully, Instagram Graph, LinkedIn, Resend). Returns permalink + provider IDs."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "pack_id": {"type": "string"},
                    "credentials_ref": {"type": "string"},
                },
                "required": ["session_id", "pack_id", "credentials_ref"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name == "content_copilot.ingest":
        result = await ingest.run(arguments["source_url"], arguments.get("kind", "auto"))
    elif name == "content_copilot.mine_moments":
        result = await mine.run(arguments["session_id"], arguments.get("top_k", 10))
    elif name == "content_copilot.pack":
        voice = load_voice_profile(arguments.get("voice_profile", "generic-founder"))
        result = await pack.run(
            arguments["session_id"], arguments["moment_id"], arguments["target"], voice
        )
    elif name == "content_copilot.ship":
        result = await ship.run(
            arguments["session_id"], arguments["pack_id"], arguments["credentials_ref"]
        )
    else:
        raise ValueError(f"unknown tool: {name}")
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]


async def main_stdio() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    asyncio.run(main_stdio())


if __name__ == "__main__":
    main()
