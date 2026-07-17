"""Gateway configuration.

All settings come from environment variables (or a local ``.env``). The OKX_*
credentials are the SELLER's credential set for the OKX Broker/Facilitator
(verify + settle) — they are never a buyer-facing gate. The x402 payment IS the
access: no accounts, no API keys for callers.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # --- OKX seller -> Broker/Facilitator credentials (settle on X Layer) -----
    okx_api_key: str = ""
    okx_secret_key: str = ""
    okx_passphrase: str = ""
    okx_base_url: str = "https://web3.okx.com"

    # --- Settlement ----------------------------------------------------------
    network: str = "eip155:196"          # OKX X Layer (CAIP-2). Only network OKX supports today.
    pay_to_address: str = ""             # X Layer wallet; receives USDT0 (0x779Ded...)
    sync_settle: bool = True             # True: block on on-chain confirm before releasing data
    max_timeout_seconds: int = 300       # payment deadline advertised in the 402 challenge
    ingest_timeout_seconds: int = 900    # ingest can download+transcribe; needs a longer window
    facilitator_timeout_seconds: float = 10.0
    # Hard per-call processing deadline: OKX platform tasks time out waiting on
    # slow agents — past this, return a fast unbilled 504 instead of hanging.
    work_deadline_seconds: int = 210

    # --- Pricing (USD; settled as USDT0 atomic units on X Layer) --------------
    # Hackathon-intro pricing: low enough that any agent can afford a full
    # pipeline run, real enough that every call is a genuine on-chain settle.
    price_ingest: str = "$0.10"
    price_mine: str = "$0.25"
    price_pack: str = "$0.50"
    price_ship: str = "$0.25"

    # --- Ledger / alerting / admin -------------------------------------------
    ledger_path: str = "/data/ledger.db"
    alert_webhook_url: str = ""
    admin_token: str = ""
    explorer_tx_base: str = "https://www.oklink.com/x-layer/tx/"

    # --- Abuse control --------------------------------------------------------
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60

    # --- Server ----------------------------------------------------------------
    port: int = 8788
    log_level: str = "INFO"
    public_base_url: str = "https://copilot.brunopessoa.com"

    def require_seller_creds(self) -> None:
        """Raise if mandatory seller/settlement config is missing."""
        missing = [
            name
            for name, val in (
                ("OKX_API_KEY", self.okx_api_key),
                ("OKX_SECRET_KEY", self.okx_secret_key),
                ("OKX_PASSPHRASE", self.okx_passphrase),
                ("PAY_TO_ADDRESS", self.pay_to_address),
            )
            if not val
        ]
        if missing:
            raise RuntimeError(
                "Missing required environment variables: " + ", ".join(missing)
            )


settings = Settings()
