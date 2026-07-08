"""Source ingest — download + transcribe, caption-first.

Strategy (cheapest reliable path wins):

1. **Captions first.** For YouTube-style sources, pull existing subtitles
   (creator-provided or auto-generated) via yt-dlp — no audio download, no
   transcription compute, ~seconds.
2. **Whisper fallback.** No captions -> download audio (yt-dlp) and transcribe
   with faster-whisper (CPU int8). Capped by ``CC_MAX_TRANSCRIBE_SECONDS`` so a
   3-hour source can't blow the payment window.
3. **Articles.** Plain-text extraction with pseudo-timestamps (reading speed)
   so the downstream mining pass works on one uniform segment shape.

Sessions are keyed by source-URL hash: repeat calls return the cached manifest
instantly. The audio file is deleted after transcription — only the transcript
is retained.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("content_copilot.ingest")

SESSION_DIR = Path(os.environ.get("CC_SESSION_DIR", "/tmp/content-copilot"))

# Whisper fallback ceiling. faster-whisper "tiny" runs ~15x realtime on CPU;
# 1500s of audio ≈ 100s of transcription — safely inside the payment window.
MAX_TRANSCRIBE_SECONDS = int(os.environ.get("CC_MAX_TRANSCRIBE_SECONDS", "1500"))
WHISPER_MODEL = os.environ.get("CC_WHISPER_MODEL", "tiny")
YTDLP_PROXY = os.environ.get("CC_YTDLP_PROXY", "")

_ARTICLE_HINTS = (".html", ".htm", "/blog/", "substack.com", "medium.com")
_MEDIA_EXTS = (".mp3", ".m4a", ".wav", ".ogg", ".mp4", ".mov", ".webm")


class IngestError(RuntimeError):
    """Source could not be ingested (bad URL, no media, download blocked...)."""


def _session_id(source_url: str) -> str:
    return "cc_" + hashlib.sha256(source_url.encode()).hexdigest()[:16]


def _ytdlp_base() -> list[str]:
    cmd = ["yt-dlp", "--no-playlist", "--socket-timeout", "20"]
    if YTDLP_PROXY:
        cmd += ["--proxy", YTDLP_PROXY]
    return cmd


async def _sh(cmd: list[str], cwd: Path | None = None, timeout: float = 240.0) -> str:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(cwd) if cwd else None,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise IngestError(f"command timed out after {timeout:.0f}s: {cmd[0]}")
    if proc.returncode != 0:
        raise IngestError(f"{cmd[0]} failed: {stderr.decode()[-500:]}")
    return stdout.decode()


# --- caption path ---------------------------------------------------------------

_VTT_TS = re.compile(
    r"(?:(\d+):)?(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(?:(\d+):)?(\d{2}):(\d{2})[.,](\d{3})"
)


def _ts_to_seconds(h: str | None, m: str, s: str, ms: str) -> float:
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_vtt(text: str) -> list[dict[str, Any]]:
    """Parse WebVTT into segments, deduping the rolling repeats of auto-subs."""
    segments: list[dict[str, Any]] = []
    cur_start: float | None = None
    cur_end: float | None = None
    cur_lines: list[str] = []
    last_text = ""

    def flush() -> None:
        nonlocal last_text
        if cur_start is None:
            return
        raw = " ".join(cur_lines)
        raw = re.sub(r"<[^>]+>", "", raw)  # strip inline timing/karaoke tags
        raw = html.unescape(re.sub(r"\s+", " ", raw)).strip()
        if not raw:
            return
        # auto-subs re-emit the previous line as rolling context; drop repeats
        if last_text:
            if raw == last_text:
                return
            if raw.startswith(last_text):
                raw = raw[len(last_text):].strip()
        if raw:
            segments.append({"start": cur_start, "end": cur_end, "text": raw})
            last_text = raw

    for line in text.splitlines():
        m = _VTT_TS.search(line)
        if m:
            flush()
            g = m.groups()
            cur_start = _ts_to_seconds(g[0], g[1], g[2], g[3])
            cur_end = _ts_to_seconds(g[4], g[5], g[6], g[7])
            cur_lines = []
        elif line.strip() and not line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
            if not line.strip().isdigit():  # skip SRT-style cue counters
                cur_lines.append(line.strip())
    flush()
    return segments


async def _try_captions(source_url: str, out_dir: Path) -> list[dict[str, Any]] | None:
    """Fetch creator or auto captions without downloading media. None if absent."""
    try:
        await _sh(
            _ytdlp_base()
            + [
                "--skip-download",
                "--write-subs",
                "--write-auto-subs",
                "--sub-format", "vtt",
                "--sub-langs", "en.*,pt.*,es.*,-live_chat",
                "-o", str(out_dir / "captions"),
                source_url,
            ],
            timeout=120.0,
        )
    except IngestError as exc:
        logger.info("caption_fetch_failed url=%s err=%s", source_url, exc)
        return None
    vtts = sorted(out_dir.glob("captions*.vtt"))
    if not vtts:
        return None
    segments = parse_vtt(vtts[0].read_text(encoding="utf-8", errors="replace"))
    for extra in vtts:
        extra.unlink(missing_ok=True)
    return segments or None


# --- whisper fallback -----------------------------------------------------------

async def _download_audio(source_url: str, out_dir: Path) -> Path:
    out = out_dir / "audio.m4a"
    await _sh(
        _ytdlp_base()
        + ["-x", "--audio-format", "m4a", "--audio-quality", "5", "-o", str(out), source_url],
        timeout=300.0,
    )
    if not out.exists():
        candidates = list(out_dir.glob("audio*"))  # yt-dlp may pick the extension
        if not candidates:
            raise IngestError("audio download produced no file")
        out = candidates[0]
    return out


def _whisper_transcribe(audio: Path) -> list[dict[str, Any]]:
    """faster-whisper CPU transcription. Runs in a thread (CPU-bound)."""
    from faster_whisper import WhisperModel

    model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    segments_iter, info = model.transcribe(str(audio), vad_filter=True)
    if info.duration and info.duration > MAX_TRANSCRIBE_SECONDS:
        raise IngestError(
            f"source is {info.duration:.0f}s long — transcription is capped at "
            f"{MAX_TRANSCRIBE_SECONDS}s. Use a source with captions, or a shorter cut."
        )
    return [
        {"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()}
        for s in segments_iter
        if s.text.strip()
    ]


# --- article path ---------------------------------------------------------------

_TAG_STRIP = re.compile(r"<(script|style|nav|header|footer|aside)[^>]*>.*?</\1>", re.S | re.I)
_TAGS = re.compile(r"<[^>]+>")
_WPM = 150.0  # pseudo-timestamps at average reading speed


async def _ingest_article(source_url: str) -> list[dict[str, Any]]:
    import httpx

    try:
        async with httpx.AsyncClient(
            timeout=30.0, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (content-copilot ingest)"},
        ) as client:
            r = await client.get(source_url)
            r.raise_for_status()
    except httpx.HTTPError as exc:
        raise IngestError(f"article fetch failed: {exc}")

    body = _TAG_STRIP.sub(" ", r.text)
    paragraphs = re.split(r"</p>|<br\s*/?>|\n\n", body)
    segments: list[dict[str, Any]] = []
    t = 0.0
    for p in paragraphs:
        text = html.unescape(_TAGS.sub(" ", p))
        text = re.sub(r"\s+", " ", text).strip()
        words = len(text.split())
        if words < 8:  # skip nav crumbs / captions / boilerplate shards
            continue
        dur = max(2.0, words / _WPM * 60.0)
        segments.append({"start": round(t, 2), "end": round(t + dur, 2), "text": text})
        t += dur
    return segments


# --- entry point ----------------------------------------------------------------

def _looks_like_article(source_url: str, kind: str) -> bool:
    if kind == "article":
        return True
    if kind in ("youtube", "podcast", "audio", "video"):
        return False
    low = source_url.lower()
    if any(low.endswith(ext) or ext + "?" in low for ext in _MEDIA_EXTS):
        return False
    if "youtube.com" in low or "youtu.be" in low:
        return False
    return any(h in low for h in _ARTICLE_HINTS)


async def run(source_url: str, kind: str = "auto") -> dict[str, Any]:
    if not source_url.lower().startswith(("http://", "https://")):
        raise IngestError("source_url must be an http(s) URL")

    sid = _session_id(source_url)
    session_dir = SESSION_DIR / sid
    session_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = session_dir / "manifest.json"
    if manifest_path.exists():
        cached = json.loads(manifest_path.read_text())
        cached["cached"] = True
        return cached

    if _looks_like_article(source_url, kind):
        segments = await _ingest_article(source_url)
        method = "article"
    else:
        segments = await _try_captions(source_url, session_dir)
        method = "captions"
        if segments is None:
            audio = await _download_audio(source_url, session_dir)
            try:
                segments = await asyncio.to_thread(_whisper_transcribe, audio)
                method = f"whisper-{WHISPER_MODEL}"
            finally:
                audio.unlink(missing_ok=True)

    if not segments:
        raise IngestError("no transcribable content found at the source URL")

    (session_dir / "transcript.json").write_text(
        json.dumps({"segments": segments}, ensure_ascii=False)
    )
    result = {
        "session_id": sid,
        "source_url": source_url,
        "kind": "article" if method == "article" else kind,
        "transcription": method,
        "segments": len(segments),
        "duration_s": round(segments[-1]["end"], 2),
        "cached": False,
    }
    manifest_path.write_text(json.dumps(result, ensure_ascii=False))
    return result
