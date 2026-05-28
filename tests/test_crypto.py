"""Tests for crypto.VendorCrypto -- launch-params encryption at rest."""
import pytest
from cryptography.fernet import Fernet

from esources.crypto import CryptoError, VendorCrypto

KEY = Fernet.generate_key().decode()


def test_round_trip_list():
    vc = VendorCrypto(KEY)
    params = ["db=BioRC", "password=example-pass", "user=your-customer-id"]
    token = vc.encrypt_params(params)
    assert token != ""
    # ciphertext doesn't leak the plaintext
    for p in params:
        assert p not in token
    assert vc.decrypt_params(token) == params


def test_empty_values():
    vc = VendorCrypto(KEY)
    assert vc.encrypt_params([]) == ""
    assert vc.encrypt_params(None) == ""
    assert vc.decrypt_params("") == []


def test_ciphertext_is_not_stable():
    # Fernet embeds a random IV -- two encryptions of the same params differ.
    vc = VendorCrypto(KEY)
    a = vc.encrypt_params(["x=1"])
    b = vc.encrypt_params(["x=1"])
    assert a != b
    assert vc.decrypt_params(a) == vc.decrypt_params(b) == ["x=1"]


def test_preserves_order_and_unicode():
    vc = VendorCrypto(KEY)
    params = ["query=café", "filter=naïve", "id=001"]
    assert vc.decrypt_params(vc.encrypt_params(params)) == params


def test_bad_key_rejected():
    with pytest.raises(CryptoError):
        VendorCrypto("not-a-valid-fernet-key")
    with pytest.raises(CryptoError):
        VendorCrypto("")


def test_decrypt_with_wrong_key_raises():
    token = VendorCrypto(KEY).encrypt_params(["secret=value"])
    other = VendorCrypto(Fernet.generate_key().decode())
    with pytest.raises(CryptoError):
        other.decrypt_params(token)


def test_decrypt_garbled_payload_raises():
    # Valid Fernet token but the cleartext isn't a JSON list -- defend
    # against any future caller misuse / format drift.
    vc = VendorCrypto(KEY)
    f = vc._fernet
    bad_token = f.encrypt(b'"just a string"').decode("ascii")
    with pytest.raises(CryptoError):
        vc.decrypt_params(bad_token)
