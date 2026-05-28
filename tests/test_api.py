"""Tests for the public JSON API (routes/api.py).

These cover the pure-function projection: confirm we expose only
public-safe fields, never expose vendor credentials, and produce a
correctly-shaped launch URL pointing at the gateway.
"""
from routes.api import _PUBLIC_FIELDS, _to_public


def _full_record() -> dict:
    """A record with every internal field populated, to verify we drop them."""
    return {
        "id": "abc123",
        "legacy_entry_id": 885,
        "name": "Academic Search Complete",
        "slug": "academic-search-complete",
        "destination_url": "https://search.ebscohost.com/login.aspx",
        "launch_params": "gAAAAA...secret-fernet-blob...",
        "in_house_access": 1,
        "remote_access": 2,
        "transfer_type": 1,
        "categories": [{"name": "General"}],
        "blocked_patron_code_ids": [2, 4],
        "description": "Scholarly articles.",
        "message": "",
        "enabled": True,
        "created_at": "2026-05-23T00:00:00Z",
        "updated_at": "2026-05-23T00:00:00Z",
    }


def test_public_fields_are_returned():
    out = _to_public(_full_record(), "https://your-eresources-domain.org")
    for f in _PUBLIC_FIELDS:
        assert f in out, f"expected {f!r} in public projection"
    assert out["name"] == "Academic Search Complete"
    assert out["legacy_entry_id"] == 885
    assert out["categories"] == [{"name": "General"}]


def test_launch_url_points_at_gateway_not_vendor():
    """The launch URL must route patrons through /go/<slug> so the gateway
    can enforce IP checks, card login, and patron-code block-lists."""
    out = _to_public(_full_record(), "https://your-eresources-domain.org")
    assert out["launch_url"] == "https://your-eresources-domain.org/go/academic-search-complete"
    # And NEVER the raw vendor URL.
    assert "ebscohost.com" not in out["launch_url"]


def test_launch_url_strips_trailing_slash_from_base():
    out = _to_public(_full_record(), "https://your-eresources-domain.org/")
    assert out["launch_url"] == "https://your-eresources-domain.org/go/academic-search-complete"


def test_credentials_are_never_returned():
    """Block-list assertions: every credential / internal-policy field
    must be absent from the projection."""
    out = _to_public(_full_record(), "https://your-eresources-domain.org")
    for forbidden in (
        "launch_params",          # Fernet-encrypted vendor credentials
        "destination_url",        # would bypass the gateway
        "blocked_patron_code_ids",  # internal access policy
        "transfer_type",          # internal launch-method hint
        "enabled",                # implicit (we only serialize enabled)
        "id",                     # Firestore internal
        "created_at",             # not useful publicly
        "updated_at",             # not useful publicly
    ):
        assert forbidden not in out, f"{forbidden!r} leaked into public projection"


def test_missing_optional_fields_yield_none():
    """A sparse record (e.g. one without a description) projects cleanly
    rather than KeyError-ing."""
    sparse = {"slug": "x", "name": "X"}
    out = _to_public(sparse, "https://your-eresources-domain.org")
    assert out["name"] == "X"
    assert out["description"] is None
    assert out["categories"] is None
    assert out["launch_url"] == "https://your-eresources-domain.org/go/x"
