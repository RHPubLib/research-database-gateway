"""Tests for ip_check — on-campus detection.

ProxyFix has already resolved request.remote_addr by the time these run, so
the tests use a fake request carrying the resolved IP directly.
"""
from types import SimpleNamespace

from esources.ip_check import client_ip, is_on_campus
from esources.util import parse_cidrs

CIDRS = parse_cidrs("198.51.100.0/24, 203.0.113.7")


def _req(remote_addr, xff=""):
    return SimpleNamespace(remote_addr=remote_addr, headers={"X-Forwarded-For": xff})


def test_client_ip():
    assert client_ip(_req("198.51.100.9")) == "198.51.100.9"
    assert client_ip(_req(None)) == ""


def test_on_campus_inside_range():
    assert is_on_campus(_req("198.51.100.250"), CIDRS) is True


def test_on_campus_single_host():
    assert is_on_campus(_req("203.0.113.7"), CIDRS) is True


def test_off_campus():
    assert is_on_campus(_req("8.8.8.8"), CIDRS) is False


def test_spoofed_xff_is_ignored():
    # A client-supplied X-Forwarded-For must not flip the decision — only the
    # ProxyFix-resolved remote_addr counts.
    spoof = _req("8.8.8.8", xff="198.51.100.1, 8.8.8.8")
    assert is_on_campus(spoof, CIDRS) is False


def test_no_cidrs_configured():
    assert is_on_campus(_req("198.51.100.9"), []) is False
