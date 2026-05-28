"""On-campus detection.

A patron browsing from inside the library reaches this service from one of
RHPL's public IP ranges, and should skip the card login — exactly as the old
Polaris esources.aspx page behaved.

Trusting the client IP behind proxies
--------------------------------------
The app runs on Cloud Run, optionally behind Firebase Hosting. Google's
infrastructure appends the real TCP peer to X-Forwarded-For. A malicious
client can *prepend* a fake IP, so we must count trusted hops from the RIGHT.

`werkzeug.middleware.proxy_fix.ProxyFix(x_for=N)` does exactly that: it sets
`request.remote_addr` to the Nth value from the end of X-Forwarded-For. N must
equal the real number of trusted proxies — too high and a client can spoof an
on-campus IP. ProxyFix is installed in app.py with N = TRUSTED_PROXY_HOPS, and
the /whoami route exists to verify N empirically before launch.

So by the time a request reaches a view, `request.remote_addr` is already the
trustworthy client IP. This module just tests it against the CIDR list.
"""
from __future__ import annotations

from util import ip_in_cidrs


def client_ip(request) -> str:
    """The patron's IP, as resolved by ProxyFix from X-Forwarded-For."""
    return (request.remote_addr or "").strip()


def is_on_campus(request, public_cidrs: list) -> bool:
    """True if the request originates from an RHPL public IP range."""
    return ip_in_cidrs(client_ip(request), public_cidrs)


def raw_forwarded_for(request) -> str:
    """The unparsed X-Forwarded-For header — for the /whoami diagnostic only."""
    return request.headers.get("X-Forwarded-For", "")
