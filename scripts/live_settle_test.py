"""Real end-to-end x402 buy against the LIVE Content Copilot gateway.

Runs the paid pipeline as a real buyer: ingest -> mine -> pack, each call paying
real USD₮0 on X Layer through the OKX Broker (402 challenge -> EIP-3009 sign ->
verify -> deliver -> on-chain settle). This is the exact flow an okx.ai buyer
agent runs — and the demo-video money shot.

Spends ~$0.85 of real USD₮0 per full run (0.10 + 0.25 + 0.50).

Usage:
    BUYER_WALLET_JSON=~/fti-x402-gateway/.buyer_wallet.json \
    python scripts/live_settle_test.py [source_url]
"""

import asyncio
import json
import os
import sys

# --- CRITICAL: replicate the gateway's USD₮0 asset-name fix on the BUYER side.
# EIP-3009 is signed client-side over the token's EIP-712 domain; if the SDK's
# default_asset.name stays "USDT" the signature is over the wrong domain and the
# Broker rejects it as invalid_signature. Must patch BEFORE building the scheme.
from x402.mechanisms.evm.constants import NETWORK_CONFIGS  # noqa: E402

_asset = NETWORK_CONFIGS.get("eip155:196", {}).get("default_asset")
if _asset is None or "name" not in _asset:
    sys.exit(f"SDK shape changed: default_asset={_asset!r}")
_asset["name"] = "USD₮0"  # U+20AE tugrik — matches the on-chain token name()

from eth_account import Account  # noqa: E402
from x402 import x402Client  # noqa: E402
from x402.http.clients.httpx import wrapHttpxWithPayment  # noqa: E402
from x402.mechanisms.evm.exact.client import ExactEvmScheme  # noqa: E402
from x402.mechanisms.evm.signers import EthAccountSigner  # noqa: E402

GATEWAY = os.environ.get("GATEWAY", "https://copilot.brunopessoa.com")
DEFAULT_SOURCE = "https://paulgraham.com/greatwork.html"


def _load_buyer() -> Account:
    path = os.path.expanduser(
        os.environ.get("BUYER_WALLET_JSON", "~/fti-x402-gateway/.buyer_wallet.json")
    )
    with open(path) as fh:
        data = json.load(fh)
    pk = data.get("private_key") or data.get("privateKey") or data.get("key")
    if not pk:
        sys.exit(f"no private key in {path} (keys={list(data)})")
    return Account.from_key(pk)


def _show(step: str, resp) -> dict:
    print(f"\n=== {step}: HTTP {resp.status_code} ===")
    pay = resp.headers.get("payment-response") or resp.headers.get("PAYMENT-RESPONSE")
    if pay:
        print(f"PAYMENT-RESPONSE: {pay[:120]}...")
    body = resp.json() if resp.status_code == 200 else {"error": resp.text[:300]}
    print(json.dumps(body, indent=2, ensure_ascii=False)[:1200])
    if resp.status_code != 200:
        sys.exit(f"{step} failed with HTTP {resp.status_code} — aborting (nothing further billed)")
    return body


async def main() -> int:
    source_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SOURCE
    buyer = _load_buyer()
    print(f"buyer:   {buyer.address}")
    print(f"gateway: {GATEWAY}")
    print(f"source:  {source_url}")

    client = x402Client()
    client.register("eip155:196", ExactEvmScheme(signer=EthAccountSigner(buyer)))

    async with wrapHttpxWithPayment(client, timeout=300.0) as http:
        r = await http.get(f"{GATEWAY}/v1/ingest", params={"source_url": source_url})
        ingested = _show("ingest ($0.10)", r)
        sid = ingested["session_id"]

        r = await http.get(f"{GATEWAY}/v1/mine", params={"session_id": sid, "top_k": 3})
        mined = _show("mine ($0.25)", r)
        top = mined["moments"][0]

        r = await http.get(
            f"{GATEWAY}/v1/pack",
            params={
                "session_id": sid,
                "moment_id": top["moment_id"],
                "target": "x",
                "voice_profile": "generic-founder",
            },
        )
        packed = _show("pack ($0.50)", r)

    print("\nFULL PIPELINE PAID + DELIVERED.")
    print(f"session: {sid}")
    print(f"pack:    {packed['pack_id']}")
    print(f"tweet:   {packed['body']['tweets'][0]!r}")
    print("\nEach step settled on-chain in USD₮0 (X Layer). Check /admin/transactions "
          "or the payTo wallet on OKLink for the tx hashes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
