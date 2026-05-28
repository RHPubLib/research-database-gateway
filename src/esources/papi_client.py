"""Polaris PAPI client — patron library-card verification.

Adapted from /var/opt/rhpl/studentupdate/pipeline/papi_client.py. That client
reads credentials from a file and performs staff-scoped patron writes; this
one needs only the public-scope patron-authenticate call and takes its config
from the constructor (Cloud Run supplies PAPI_API_SECRET from Secret Manager).

Auth: PWS HMAC-SHA1 request signing in the "polaris.js" format —
    signature = base64(HMAC-SHA1(method + full_url + date + secret, api_secret))

Two calls, both public scope:

  AuthenticatePatron:
    POST /REST/public/v1/{LangID}/{AppID}/{OrgID}/authenticator/patron
    body: {"Barcode": "<bc>", "Password": "<pin>"}
    signed with secret = ""
    -> yes/no; returns PatronID + AccessSecret but NOT PatronCodeID.

  PatronBasicDataGet:
    GET /REST/public/v1/{LangID}/{AppID}/{OrgID}/patron/{barcode}/basicdata
    signed with secret = "<pin>" (Polaris uses the PIN as the patron token)
    -> returns the patron's PatronCodeID, used to enforce per-resource
       block-lists (7 databases need this).

    PAPIErrorCode  0     -> success (on AuthenticatePatron, may also be a
                            positive row-count integer per Polaris docs)
    PAPIErrorCode -3001  -> AuthenticatePatron: unable to authenticate
                            (covers both bad barcode AND bad PIN; Polaris
                            does NOT distinguish for AuthenticatePatron)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from email.utils import formatdate

# PAPI error codes worth naming. Failure codes are surfaced to patrons with
# the SAME generic message so the form never reveals which field is wrong.
ERR_OK = 0
ERR_AUTH_FAILED = -3001         # AuthenticatePatron: bad barcode or bad PIN
ERR_PATRON_NOT_FOUND = -6000    # other patron-scope methods only
ERR_INVALID_PASSWORD = -6001    # other patron-scope methods only


class PapiError(RuntimeError):
    """Raised for transport-level failures (DNS, TLS, timeout, connection)."""


@dataclass
class PapiResponse:
    status_code: int
    body: dict
    raw_text: str

    @property
    def papi_error_code(self) -> int:
        if isinstance(self.body, dict) and "PAPIErrorCode" in self.body:
            try:
                return int(self.body["PAPIErrorCode"])
            except (TypeError, ValueError):
                return -999
        return -999

    @property
    def ok(self) -> bool:
        """True only when the HTTP call AND the PAPI operation both succeeded."""
        return 200 <= self.status_code < 300 and self.papi_error_code == ERR_OK


class PapiClient:
    """Minimal Polaris PAPI client for patron card verification."""

    def __init__(
        self,
        *,
        base_url: str,
        lang_id: str,
        app_id: str,
        org_id: str,
        api_access_id: str,
        api_secret: str,
        timeout: int = 15,
    ):
        self.base_url = base_url.rstrip("/")
        self.lang_id = lang_id
        self.app_id = app_id
        self.org_id = org_id
        self.api_access_id = api_access_id
        self._api_secret = api_secret.encode("utf-8")
        self.timeout = timeout

    def _sign(self, method: str, full_url: str, date_str: str, secret: str = "") -> str:
        encoding = f"{method}{full_url}{date_str}{secret}"
        digest = hmac.new(self._api_secret, encoding.encode("utf-8"), hashlib.sha1).digest()
        return base64.b64encode(digest).decode("ascii")

    def _public_prefix(self) -> str:
        return f"/REST/public/v1/{self.lang_id}/{self.app_id}/{self.org_id}"

    def _request(self, method: str, path: str, body: dict | None = None,
                 secret: str = "") -> PapiResponse:
        date_str = formatdate(usegmt=True)
        full_url = self.base_url + path
        sig = self._sign(method, full_url, date_str, secret)

        headers = {
            "Authorization": f"PWS {self.api_access_id}:{sig}",
            "PolarisDate": date_str,
            "Accept": "application/json",
        }
        data: bytes | None = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(full_url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status = resp.status
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            # PAPI returns a JSON body with PAPIErrorCode even on 4xx.
            status = exc.code
            raw = exc.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise PapiError(f"PAPI connection error: {exc}") from exc

        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {}
        return PapiResponse(status_code=status, body=parsed, raw_text=raw)

    def patron_authenticate(self, barcode: str, pin: str) -> PapiResponse:
        """Verify a library card barcode + PIN against Polaris.

        Caller treats only `response.ok` as success. ERR_AUTH_FAILED (-3001)
        covers both bad-barcode and bad-PIN — Polaris's AuthenticatePatron
        does not distinguish, which is helpful for the form's "card or PIN"
        wording (no field-level disclosure).
        """
        path = f"{self._public_prefix()}/authenticator/patron"
        return self._request("POST", path, body={
            "Barcode": (barcode or "").strip(),
            "Password": pin or "",
        })

    def patron_basic_data(self, barcode: str, pin: str) -> PapiResponse:
        """Fetch the patron's basic data (incl. PatronCodeID).

        Signed with the patron PIN as the HMAC secret slot, per Polaris's
        public-scope patron-resource convention. A successful response
        implies the PIN was valid -- but we still call patron_authenticate
        first so a clean yes/no precedes the data fetch.
        """
        bc = urllib.parse.quote((barcode or "").strip(), safe="")
        path = f"{self._public_prefix()}/patron/{bc}/basicdata"
        return self._request("GET", path, secret=pin or "")

    @staticmethod
    def extract_patron_code_id(resp: PapiResponse) -> int | None:
        """Pull PatronCodeID out of a basicdata response, or None if absent.

        Polaris's JSON envelope nests the patron fields under "PatronBasicData"
        in some versions and inlines them in others; try both.
        """
        if not isinstance(resp.body, dict):
            return None
        for container in (resp.body, resp.body.get("PatronBasicData") or {}):
            if not isinstance(container, dict):
                continue
            val = container.get("PatronCodeID")
            if val is None:
                continue
            try:
                return int(val)
            except (TypeError, ValueError):
                return None
        return None
