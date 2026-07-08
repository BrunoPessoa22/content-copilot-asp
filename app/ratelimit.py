"""In-process sliding-window rate limiter.

A money endpoint with NO abuse control is the single biggest go-live risk
(verification is free; only settlement costs the buyer, so an attacker can hammer
the upstream FTI API — via our internal key — for free). This adds a per-client
cap at the app layer so a flood is rejected with 429 before it reaches the
paywall or, worse, the internal-key upstream call.

Scope: process-local (per replica). For a single Coolify container this is the
whole surface; if the gateway is ever scaled horizontally, add a shared store
(Redis) or enforce the same cap at Traefik. Deliberately dependency-free.
"""

import threading
import time
from collections import defaultdict, deque

_lock = threading.Lock()
_hits: dict[str, deque[float]] = defaultdict(deque)
# Hard cap on tracked keys so a spray of distinct IPs can't grow memory unbounded.
_MAX_KEYS = 50_000


def allow(key: str, limit: int, window_seconds: float, *, now: float | None = None) -> bool:
    """Return True if `key` is under `limit` events in the trailing window.

    Records the event when allowed. O(evicted) amortized; the deque holds at most
    `limit` timestamps per key.
    """
    t = time.monotonic() if now is None else now
    cutoff = t - window_seconds
    with _lock:
        if len(_hits) > _MAX_KEYS:
            _gc(cutoff)
        dq = _hits[key]
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= limit:
            return False
        dq.append(t)
        return True


def retry_after(key: str, window_seconds: float, *, now: float | None = None) -> int:
    """Seconds until the oldest in-window event for `key` expires (for Retry-After)."""
    t = time.monotonic() if now is None else now
    with _lock:
        dq = _hits.get(key)
        if not dq:
            return 1
        return max(1, int(window_seconds - (t - dq[0])) + 1)


def _gc(cutoff: float) -> None:
    """Drop keys whose newest event is already outside the window (caller holds lock)."""
    stale = [k for k, dq in _hits.items() if not dq or dq[-1] < cutoff]
    for k in stale:
        del _hits[k]


def reset() -> None:
    """Test helper: clear all state."""
    with _lock:
        _hits.clear()
