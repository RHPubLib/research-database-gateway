"""Configuration for the RHPL eResources service.

All settings come from environment variables. In production Cloud Run injects
them: plain config via --set-env-vars, secrets via --set-secrets (Secret
Manager). For local development, put them in a .env file (see .env.example)
and load it before importing the app.

`load_config()` builds and validates a Config; the app factory calls it once
at startup so a misconfigured deployment fails fast and loudly.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from util import parse_cidrs


@dataclass(frozen=True)
class Config:
    # GCP / Firestore
    gcp_project: str

    # Public site
    public_base_url: str

    # Flask session
    secret_key: str
    session_minutes: int

    # On-campus detection
    public_cidrs: list = field(default_factory=list)
    trusted_proxy_hops: int = 2

    # Staff admin OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    admin_email_domain: str = "rhpl.org"

    # Vendor-password encryption
    fernet_key: str = ""

    # Polaris PAPI
    papi_base_url: str = "https://your-polaris-server/PAPIService"
    papi_lang_id: str = "1033"
    papi_app_id: str = "100"
    papi_org_id: str = "3"
    papi_api_access_id: str = "localpull"
    papi_api_secret: str = ""

    # Login rate limiting
    login_rate_max: int = 5
    login_rate_window_min: int = 15

    # Debug
    enable_whoami: bool = False


def _require(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise RuntimeError(
            f"Required environment variable {name} is missing or empty. "
            "See .env.example."
        )
    return val


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {name}={raw!r} is not an integer") from exc


def load_config() -> Config:
    """Build a Config from the environment, raising on missing required values."""
    cfg = Config(
        gcp_project=_require("GCP_PROJECT"),
        public_base_url=_require("PUBLIC_BASE_URL").rstrip("/"),
        secret_key=_require("SECRET_KEY"),
        session_minutes=_int("SESSION_MINUTES", 30),
        public_cidrs=parse_cidrs(os.environ.get("PUBLIC_CIDRS", "")),
        trusted_proxy_hops=_int("TRUSTED_PROXY_HOPS", 2),
        google_client_id=_require("GOOGLE_CLIENT_ID"),
        google_client_secret=_require("GOOGLE_CLIENT_SECRET"),
        admin_email_domain=os.environ.get("ADMIN_EMAIL_DOMAIN", "rhpl.org").strip().lower(),
        fernet_key=_require("FERNET_KEY"),
        papi_base_url=os.environ.get("PAPI_BASE_URL", "https://your-polaris-server/PAPIService").rstrip("/"),
        papi_lang_id=os.environ.get("PAPI_LANG_ID", "1033").strip(),
        papi_app_id=os.environ.get("PAPI_APP_ID", "100").strip(),
        papi_org_id=os.environ.get("PAPI_ORG_ID", "3").strip(),
        papi_api_access_id=os.environ.get("PAPI_API_ACCESS_ID", "localpull").strip(),
        papi_api_secret=_require("PAPI_API_SECRET"),
        login_rate_max=_int("LOGIN_RATE_MAX", 5),
        login_rate_window_min=_int("LOGIN_RATE_WINDOW_MIN", 15),
        enable_whoami=os.environ.get("ENABLE_WHOAMI", "").strip() in ("1", "true", "True"),
    )
    if not cfg.public_cidrs:
        # Not fatal — the service still works, every off-site patron just gets
        # the card login. But it almost certainly means a misconfiguration.
        import logging
        logging.getLogger("esources").warning(
            "PUBLIC_CIDRS is empty — no patron will be treated as on-campus."
        )
    return cfg
