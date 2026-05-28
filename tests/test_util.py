"""Tests for util.py — slug generation, CIDR parsing, URL validation."""
from util import (ip_in_cidrs, is_http_url, parse_cidrs, slugify,
                  unique_slug)


def test_slugify_basic():
    assert slugify("Gale Literature: LitFinder") == "gale-literature-litfinder"
    assert slugify("ProQuest") == "proquest"


def test_slugify_accents_and_punctuation():
    assert slugify("Référence & Co.") == "reference-co"
    assert slugify("A to Z   Databases!!!") == "a-to-z-databases"


def test_slugify_empty():
    assert slugify("") == ""
    assert slugify("   ") == ""
    assert slugify("!@#$%") == ""


def test_unique_slug_no_collision():
    assert unique_slug("ProQuest", set()) == "proquest"


def test_unique_slug_collisions():
    taken = {"proquest", "proquest-2"}
    assert unique_slug("ProQuest", taken) == "proquest-3"


def test_unique_slug_unsluggable_name():
    assert unique_slug("!!!", set()) == "database"


def test_parse_cidrs_good_and_bad():
    nets = parse_cidrs("198.51.100.0/24, 203.0.113.5, garbage, 10.0.0.0/8")
    # garbage is skipped; bare IP becomes a host network
    assert len(nets) == 3


def test_parse_cidrs_empty():
    assert parse_cidrs("") == []
    assert parse_cidrs(None) == []


def test_ip_in_cidrs():
    nets = parse_cidrs("198.51.100.0/24")
    assert ip_in_cidrs("198.51.100.42", nets) is True
    assert ip_in_cidrs("203.0.113.1", nets) is False
    assert ip_in_cidrs("not-an-ip", nets) is False
    assert ip_in_cidrs("198.51.100.42", []) is False


def test_is_http_url():
    assert is_http_url("https://example.com")
    assert is_http_url("http://example.com")
    assert not is_http_url("ftp://example.com")
    assert not is_http_url("javascript:alert(1)")
    assert not is_http_url("")
