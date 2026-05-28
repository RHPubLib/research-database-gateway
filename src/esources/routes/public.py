"""Patron-facing routes: the database listing and the access gateway.

Gateway flow for /go/<slug>, replicating the legacy Polaris esources.aspx
behaviour using Polaris's own InHouseAccess / RemoteAccess enums (see
gateway.decide_access for the matrix):

    in-library + InHouseAccess=1/3   -> straight through
    in-library + InHouseAccess=2     -> card login, then through
    off-site   + RemoteAccess=1      -> straight through
    off-site   + RemoteAccess=2      -> card login, then through
    off-site   + RemoteAccess=3      -> "available in the library only"
    after login + allow-list mismatch -> "not eligible with your card type"

A successful card login sets a signed session flag good for SESSION_MINUTES
across every resource -- the patron verifies once per visit, not per database.
"""
from __future__ import annotations

import logging
import time

from flask import (Blueprint, current_app, make_response, redirect,
                   render_template, request, session, url_for)

from ..crypto import CryptoError
from ..gateway import (DENY_OFFSITE, DENY_PATRON_CODE, GRANT, LOGIN,
                     decide_access)
from ..ip_check import client_ip, is_on_campus, raw_forwarded_for
from ..papi_client import PapiError

log = logging.getLogger("esources.public")
bp = Blueprint("public", __name__)


def _svc():
    return current_app.extensions["esources"]


def _session_authed() -> bool:
    """True if the browser holds a valid, non-expired card-verified session."""
    return bool(session.get("esources_auth")) and \
        float(session.get("esources_exp", 0)) > time.time()


def _session_patron_code() -> int | None:
    """The authed patron's PatronCodeID, or None if no session / not captured."""
    if not _session_authed():
        return None
    raw = session.get("esources_patron_code_id")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _grant_session(patron_code_id: int | None) -> None:
    svc = _svc()
    session.permanent = True
    session["esources_auth"] = True
    session["esources_exp"] = time.time() + svc.config.session_minutes * 60
    session["esources_patron_code_id"] = (
        int(patron_code_id) if patron_code_id is not None else None
    )


def _decide(rec: dict) -> str:
    """Run the gateway against the current request + record."""
    svc = _svc()
    return decide_access(
        on_campus=is_on_campus(request, svc.config.public_cidrs),
        authed=_session_authed(),
        in_house_access=int(rec.get("in_house_access") or 3),
        remote_access=int(rec.get("remote_access") or 2),
        patron_code_id=_session_patron_code(),
        blocked_patron_code_ids=rec.get("blocked_patron_code_ids") or [],
    )


# --- Listing ----------------------------------------------------------------

@bp.route("/")
def listing():
    recs = _svc().store.list_enabled()

    # Each record carries categories=[{name}, ...]; explode the list so a
    # database cross-listed in N categories renders N times. Categories
    # sort alphabetically; items within a category sort by name.
    by_cat: dict[str, list] = {}
    for r in recs:
        placements = r.get("categories") or []
        if not placements:
            placements = [{"name": "Databases"}]
        for p in placements:
            name = (p.get("name") or "Databases").strip() or "Databases"
            by_cat.setdefault(name, []).append(r)

    groups = []
    for cat in sorted(by_cat, key=lambda c: c.lower()):
        items = sorted(by_cat[cat], key=lambda r: (r.get("name") or "").lower())
        groups.append((cat, items))

    return render_template("listing.html", groups=groups, total=len(recs))


# --- Health / diagnostics ---------------------------------------------------

@bp.route("/healthz")
def healthz():
    return {"status": "ok"}, 200


@bp.route("/whoami")
def whoami():
    """IP-detection diagnostic. Enabled by ENABLE_WHOAMI; use it to confirm
    TRUSTED_PROXY_HOPS is correct before trusting the on-campus bypass."""
    svc = _svc()
    if not svc.config.enable_whoami:
        return render_template("error.html", title="Not found",
                               message="That page could not be found."), 404
    ip = client_ip(request)
    return {
        "resolved_client_ip": ip,
        "on_campus": is_on_campus(request, svc.config.public_cidrs),
        "trusted_proxy_hops": svc.config.trusted_proxy_hops,
        "x_forwarded_for": raw_forwarded_for(request),
    }, 200


# --- Access gateway ---------------------------------------------------------

def _lookup_enabled(slug: str):
    rec = _svc().store.get_by_slug(slug)
    if not rec or not rec.get("enabled"):
        return None
    return rec


@bp.route("/go/<slug>")
def go(slug):
    rec = _lookup_enabled(slug)
    if rec is None:
        return render_template("error.html", title="Resource not found",
                               message="That database is not available."), 404

    action = _decide(rec)
    if action == GRANT:
        return redirect(url_for("public.access", slug=slug))
    if action == DENY_OFFSITE:
        return render_template("error.html", title=rec["name"],
                               message="This resource is licensed for use inside "
                                       "the library only. Please visit any RHPL "
                                       "location to use it."), 200
    if action == DENY_PATRON_CODE:
        return render_template("error.html", title=rec["name"],
                               message="Your library account type isn't eligible "
                                       "for this resource. Please contact RHPL "
                                       "for help."), 200
    return redirect(url_for("public.login", slug=slug))


@bp.route("/go/<slug>/login", methods=["GET", "POST"])
def login(slug):
    rec = _lookup_enabled(slug)
    if rec is None:
        return render_template("error.html", title="Resource not found",
                               message="That database is not available."), 404

    # Already through the gate (in-library IP or active session)? Skip the form.
    action = _decide(rec)
    if action == GRANT:
        return redirect(url_for("public.access", slug=slug))
    if action == DENY_OFFSITE:
        return redirect(url_for("public.go", slug=slug))
    if action == DENY_PATRON_CODE:
        return redirect(url_for("public.go", slug=slug))

    if request.method == "GET":
        return render_template("card_login.html", resource=rec)

    # --- POST: verify the library card ---
    svc = _svc()
    barcode = (request.form.get("barcode") or "").strip()
    pin = request.form.get("pin") or ""
    ip = client_ip(request)

    rl_keys = [f"ip:{ip}"]
    if barcode:
        rl_keys.append(f"bc:{barcode}")

    blocked = svc.ratelimiter.any_blocked(rl_keys)
    if blocked.blocked:
        minutes = max(1, blocked.retry_after_seconds // 60)
        return render_template(
            "card_login.html", resource=rec,
            error=f"Too many attempts. Please wait about {minutes} minute(s) "
                  "and try again.",
        ), 429

    if not barcode or not pin:
        return render_template("card_login.html", resource=rec,
                               error="Please enter both your card number and PIN."), 400

    for key in rl_keys:
        svc.ratelimiter.record(key)

    try:
        auth_resp = svc.papi.patron_authenticate(barcode, pin)
    except PapiError as exc:
        log.error("PAPI transport error (authenticate): %s", exc)
        return render_template("card_login.html", resource=rec,
                               error="The verification service is temporarily "
                                     "unavailable. Please try again shortly."), 502

    if not auth_resp.ok:
        # ERR_PATRON_NOT_FOUND and ERR_INVALID_PASSWORD get identical wording
        # on purpose -- never reveal which field was wrong.
        log.info("card login failed: ip=%s papi_error=%s",
                 ip, auth_resp.papi_error_code)
        return render_template("card_login.html", resource=rec,
                               error="That card number or PIN was not recognized. "
                                     "Please check and try again."), 401

    # Auth ok. Fetch basic data to capture PatronCodeID for allow-list checks.
    patron_code_id: int | None = None
    try:
        bd = svc.papi.patron_basic_data(barcode, pin)
        if bd.ok:
            patron_code_id = svc.papi.extract_patron_code_id(bd)
        else:
            log.warning("basicdata returned non-ok after successful auth: %s",
                        bd.papi_error_code)
    except PapiError as exc:
        # Non-fatal: a session without a captured code still works for the
        # 99% of resources with no allow-list. Resources with a non-empty
        # allow-list will fail closed (DENY_PATRON_CODE).
        log.warning("PAPI transport error (basicdata): %s", exc)

    # Success -- clear counters so an honest mistyper isn't left locked out.
    for key in rl_keys:
        svc.ratelimiter.clear(key)
    _grant_session(patron_code_id)
    log.info("card login ok: ip=%s patron_code=%s", ip, patron_code_id)
    return redirect(url_for("public.access", slug=slug))


@bp.route("/go/<slug>/access")
def access(slug):
    rec = _lookup_enabled(slug)
    if rec is None:
        return render_template("error.html", title="Resource not found",
                               message="That database is not available."), 404

    action = _decide(rec)
    if action == LOGIN:
        return redirect(url_for("public.login", slug=slug))
    if action == DENY_OFFSITE:
        return render_template("error.html", title=rec["name"],
                               message="This resource is licensed for use inside "
                                       "the library only."), 200
    if action == DENY_PATRON_CODE:
        return render_template("error.html", title=rec["name"],
                               message="Your library account type isn't eligible "
                                       "for this resource."), 200

    # GRANTED. Decrypt launch params and ship them to the vendor.
    #
    # Transport mirrors what Polaris's classic-PAC esourceview.aspx does:
    #   * If the resource has launch_params, render an auto-submitting POST
    #     form. The URL's existing query string AND the launch_params go to
    #     the vendor in separate channels (URL query vs form body), which
    #     is critical for resources like Gale Legal Forms or EBSCO
    #     search.ebscohost.com where the URL ALREADY contains parameter
    #     names that overlap with launch_params (e.g. Gale URL has
    #     `?u=your-institution-id` and a launch_param is also `u=your-institution-id`).
    #     Appending both into one GET query string yields an ambiguous
    #     `?u=X&u=X` that vendors' parsers misread, landing patrons on
    #     404 or 400 pages.
    #   * If the resource has no launch_params, 302-redirect to the URL.
    #     Nothing to collide with; cleaner UX.
    #
    # ESourceTransferTypeID is preserved on the record for staff visibility
    # but is NOT used here -- Polaris's runtime behaviour does not actually
    # correlate with that attribute (verified 2026-05-23: Polaris POSTs
    # records with transfer_type=1 e.g. Consumer Reports just like it
    # POSTs records with transfer_type=2 e.g. Gale Legal Forms).
    svc = _svc()
    try:
        params = svc.crypto.decrypt_params(rec.get("launch_params") or "")
    except CryptoError as exc:
        log.error("launch_params decrypt failed for %s: %s", slug, exc)
        return render_template("error.html", title=rec["name"],
                               message="This database can't be opened right now. "
                                       "Please report this to the library."), 500

    if params:
        # Split each "key=value" string into (key, value), splitting only on
        # the FIRST '=' since vendor values can contain '=' (e.g. base64).
        pairs = []
        for p in params:
            if "=" in p:
                k, _, v = p.partition("=")
                pairs.append((k, v))
        resp = make_response(render_template(
            "launch_post.html",
            name=rec["name"],
            action_url=rec["destination_url"],
            params=pairs,
        ))
    else:
        resp = make_response(redirect(rec["destination_url"], code=302))
    # Credentials are in the response body (or 302 Location URL) -- never
    # let a browser, intermediary, or back-button restore cache it.
    resp.headers["Cache-Control"] = "no-store"
    return resp


# --- Embeddable iframe page -------------------------------------------------

@bp.route("/embed")
def embed():
    """Iframe-friendly catalog page for embedding in Wix or other CMSes.

    Renders the same database listing as `/` but as a standalone document
    suitable for `<iframe src=".../embed">`. The HTML is tiny -- it fetches
    /api/databases.json client-side so the data stays fresh and the
    iframe shell can be aggressively cached.

    Frame-ancestors is widened to allow embedding from rhpl.org and any
    *.wixstudio.com / *.wix.com / *.editorx.io property (Wix Studio
    publishes test sites under wixstudio.com subdomains, and the editor
    serves preview frames from editor.wix.com). If we ever embed from
    another host, add it here.
    """
    resp = make_response(render_template("embed.html"))
    # The default site-wide CSP / X-Frame-Options would block iframing.
    # Allow only the hosts we actually embed from.
    resp.headers["Content-Security-Policy"] = (
        "frame-ancestors 'self' "
        "https://*.rhpl.org "
        "https://*.wixsite.com "
        "https://*.wixstudio.com "
        "https://*.wix.com "
        "https://*.editorx.io"
    )
    # The shell itself is identical across patrons; let the CDN cache it.
    # The JSON payload it fetches has its own 5-minute Cache-Control.
    resp.headers["Cache-Control"] = "public, max-age=60"
    return resp


# --- Legacy bookmark compatibility ------------------------------------------

@bp.route("/esources")
def legacy_target():
    """Re-point old `.../esources.aspx?Target=NNN` bookmarks.

    NNN is the Polaris DWIEntries.EntryID, preserved on each record as
    `legacy_entry_id`.
    """
    raw = request.args.get("Target", "").strip()
    if not raw.isdigit():
        return render_template("error.html", title="Resource not found",
                               message="That database link is not valid."), 404
    rec = _svc().store.get_by_legacy_id(int(raw))
    if rec is None:
        return render_template("error.html", title="Resource not found",
                               message="That database is no longer available."), 404
    return redirect(url_for("public.go", slug=rec["slug"]))
