"""Read-only JSON API for the public catalog.

Exposes the same enabled-records dataset the patron listing page renders,
in a form a Wix Velo "page code" block (or any other consumer) can fetch
and render natively. Used by the rhpl.org / rhpl-studio research-databases
page to display the catalog without iframing your-eresources-domain.org.

What this endpoint exposes
--------------------------
Public-safe fields only -- the same information already visible on the
patron-facing listing page at https://your-eresources-domain.org/. In particular:
  - `launch_url` is the gateway URL (/go/<slug>), NOT the vendor URL.
    Sending patrons through the gateway preserves IP detection, card
    login, patron-code block-list enforcement, and POST-form launches.
  - `launch_params` (Fernet-encrypted credentials) is NEVER returned.
  - `destination_url`, `blocked_patron_code_ids`, and `transfer_type`
    are internal-only and not returned.

CORS
----
The dataset is already public, so the endpoint returns
`Access-Control-Allow-Origin: *` to make it trivially fetchable from
any Wix site, the Velo backend, or a static page. Do not move
sensitive fields into this response without revisiting that.
"""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, make_response

bp = Blueprint("api", __name__, url_prefix="/api")


# Fields copied verbatim from each Firestore record. Keep this list explicit
# (allow-list, not deny-list) so a future field addition does not accidentally
# leak credentials or internal policy.
_PUBLIC_FIELDS = (
    "legacy_entry_id",
    "name",
    "slug",
    "description",
    "message",
    "categories",
    "in_house_access",
    "remote_access",
)


def _to_public(rec: dict, base_url: str) -> dict:
    """Project a Firestore record down to its public-safe fields and add a
    derived `launch_url` pointing at the gateway."""
    out = {k: rec.get(k) for k in _PUBLIC_FIELDS}
    out["launch_url"] = f"{base_url.rstrip('/')}/go/{rec.get('slug', '')}"
    return out


@bp.route("/databases.json")
def databases_json():
    svc = current_app.extensions["esources"]
    recs = svc.store.list_enabled()
    payload = {
        "count": len(recs),
        "databases": [_to_public(r, svc.config.public_base_url) for r in recs],
    }
    resp = make_response(jsonify(payload))
    # Public, cacheable for 5 minutes -- the catalog changes rarely and the
    # admin UI is the only writer. Firebase Hosting / browsers can cache.
    resp.headers["Cache-Control"] = "public, max-age=300"
    # Public data; permissive CORS so Velo page code or any other client
    # can fetch from any origin.
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp
