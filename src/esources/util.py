"""Small pure-stdlib helpers shared across the app.

Kept dependency-free (no Flask, Firestore, or cryptography imports) so the
unit tests can exercise them without the full runtime installed.
"""
from __future__ import annotations

import ipaddress
import re
import unicodedata

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """Turn a database name into a URL-safe slug.

    "Gale Literature: LitFinder" -> "gale-literature-litfinder"
    Returns "" for input that has no slug-able characters.
    """
    if not name:
        return ""
    # Fold accents to ASCII so e.g. "Référence" -> "reference".
    norm = unicodedata.normalize("NFKD", name)
    norm = norm.encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_STRIP.sub("-", norm.lower()).strip("-")
    return slug


def unique_slug(name: str, taken: set) -> str:
    """slugify(name), suffixed with -2, -3, ... if it collides with `taken`.

    Does not mutate `taken`; the caller adds the returned value.
    """
    base = slugify(name) or "database"
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


def parse_cidrs(raw: str) -> list:
    """Parse a comma/whitespace-separated string of CIDRs into network objects.

    Bad entries are skipped (a warning is the caller's job). Accepts plain IPs
    too (treated as /32 or /128).
    """
    nets = []
    for chunk in re.split(r"[,\s]+", raw or ""):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            nets.append(ipaddress.ip_network(chunk, strict=False))
        except ValueError:
            continue
    return nets


def ip_in_cidrs(ip_str: str, nets: list) -> bool:
    """True if ip_str falls inside any network in `nets`."""
    if not ip_str or not nets:
        return False
    try:
        ip = ipaddress.ip_address(ip_str.strip())
    except ValueError:
        return False
    return any(ip in net for net in nets)


def is_http_url(value: str) -> bool:
    """True only for http:// or https:// URLs — used to validate redirect targets."""
    if not value:
        return False
    v = value.strip().lower()
    return v.startswith("http://") or v.startswith("https://")
