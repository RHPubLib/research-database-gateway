"""Tests for papi_client — request signing and response interpretation.

No network: these exercise the pure signing logic and the PapiResponse
success/error semantics.
"""
from papi_client import (ERR_INVALID_PASSWORD, ERR_PATRON_NOT_FOUND,
                         PapiClient, PapiResponse)


def _client():
    return PapiClient(
        base_url="https://catalog.example.org/PAPIService",
        lang_id="1033", app_id="100", org_id="3",
        api_access_id="localpull", api_secret="test-secret",
    )


def test_sign_is_deterministic_and_base64():
    c = _client()
    sig1 = c._sign("POST", "https://x/y", "Wed, 21 May 2026 00:00:00 GMT")
    sig2 = c._sign("POST", "https://x/y", "Wed, 21 May 2026 00:00:00 GMT")
    assert sig1 == sig2
    # base64 of a SHA-1 digest is 28 chars ending in '='
    assert len(sig1) == 28 and sig1.endswith("=")


def test_sign_varies_with_input():
    c = _client()
    base = c._sign("POST", "https://x/y", "DATE")
    assert c._sign("GET", "https://x/y", "DATE") != base
    assert c._sign("POST", "https://x/z", "DATE") != base
    assert c._sign("POST", "https://x/y", "OTHER") != base


def test_public_prefix():
    assert _client()._public_prefix() == "/REST/public/v1/1033/100/3"


def test_response_ok_only_on_2xx_and_code_zero():
    assert PapiResponse(200, {"PAPIErrorCode": 0}, "").ok is True


def test_response_not_ok_on_papi_error():
    bad_pin = PapiResponse(200, {"PAPIErrorCode": ERR_INVALID_PASSWORD}, "")
    no_patron = PapiResponse(200, {"PAPIErrorCode": ERR_PATRON_NOT_FOUND}, "")
    assert bad_pin.ok is False
    assert no_patron.ok is False
    assert bad_pin.papi_error_code == -6001
    assert no_patron.papi_error_code == -6000


def test_response_not_ok_on_http_error():
    assert PapiResponse(500, {"PAPIErrorCode": 0}, "").ok is False


def test_response_missing_error_code():
    assert PapiResponse(200, {}, "").papi_error_code == -999
    assert PapiResponse(200, {}, "").ok is False


# --- PatronCodeID extraction (basicdata response) --------------------------

def test_extract_patron_code_id_top_level():
    resp = PapiResponse(200, {"PAPIErrorCode": 1, "PatronCodeID": 7}, "")
    assert PapiClient.extract_patron_code_id(resp) == 7


def test_extract_patron_code_id_nested():
    # Polaris sometimes wraps the patron fields in PatronBasicData
    resp = PapiResponse(200, {
        "PAPIErrorCode": 1,
        "PatronBasicData": {"PatronCodeID": 14, "PatronID": 999},
    }, "")
    assert PapiClient.extract_patron_code_id(resp) == 14


def test_extract_patron_code_id_handles_string():
    resp = PapiResponse(200, {"PatronCodeID": "3"}, "")
    assert PapiClient.extract_patron_code_id(resp) == 3


def test_extract_patron_code_id_missing_or_bad():
    assert PapiClient.extract_patron_code_id(PapiResponse(200, {}, "")) is None
    assert PapiClient.extract_patron_code_id(
        PapiResponse(200, {"PatronCodeID": "x"}, "")) is None
    assert PapiClient.extract_patron_code_id(
        PapiResponse(200, "not a dict", "")) is None
