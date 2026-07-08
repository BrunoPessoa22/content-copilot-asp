"""Content Copilot MCP server.

Exposes four verbs — ingest, mine_moments, pack, ship — as MCP tools.
Ready to be listed on OKX.AI as an Agent-to-MCP service. The OKX Payment
SDK hook is a single call site (see ``bill_call``); until it's wired the
server runs free for local development.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from . import ingest, mine, pack, ship
from .voice_dna import load_voice_profile


PRICING_USDG = {
    "ingest": 0.50,
    "mine_moments": 1.00,
    "pack": 2.00,
    "ship": 1.00,
}


def bill_call(tool: str, caller_agent: str | None) -> None:
    """OKX Payment SDK hook — settle a per-call charge on X Layer.

    Real implementation calls the OKX Payment SDK once creds are provisioned.
    For local dev this is a no-op that logs to stderr so we can see the meter.
    """
    price = PRICING_USDG[tool]
    print(
        json.dumps({"event": "bill", "tool": tool, "caller": caller_agent, "price_usdg": price}),
        file=sys.stderr,
    )


server = Server("content-copilot")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="content_copilot.ingest",
            description=(
                "Download and transcribe a raw source (YouTube, podcast RSS episode, "
                "MP3/MP4 URL, PDF). Returns a session_id used by every downstream verb."
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
                "Publish a pack through the caller-supplied downstream (Typefully, "
                "Instagram Graph, LinkedIn, Resend). Returns permalink + provider IDs."
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
    caller = arguments.pop("_caller_agent", None)
    if name == "content_copilot.ingest":
        bill_call("ingest", caller)
        result = await ingest.run(arguments["source_url"], arguments.get("kind", "auto"))
    elif name == "content_copilot.mine_moments":
        bill_call("mine_moments", caller)
        result = await mine.run(arguments["session_id"], arguments.get("top_k", 10))
    elif name == "content_copilot.pack":
        bill_call("pack", caller)
        voice = load_voice_profile(arguments.get("voice_profile", "generic-founder"))
        result = await pack.run(
            arguments["session_id"], arguments["moment_id"], arguments["target"], voice
        )
    elif name == "content_copilot.ship":
        bill_call("ship", caller)
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
    p = argparse.ArgumentParser()
    p.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8787)))
    args = p.parse_args()
    if args.transport == "stdio":
        asyncio.run(main_stdio())
    else:
        from mcp.server.sse import SseServerTransport
        import uvicorn
        from starlette.applications import Starlette
        from starlette.routing import Mount, Route

        sse = SseServerTransport("/messages/")

        async def handle_sse(request):
            async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
                await server.run(streams[0], streams[1], server.create_initialization_options())

        app = Starlette(
            routes=[Route("/sse", endpoint=handle_sse), Mount("/messages/", app=sse.handle_post_message)]
        )
        uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
