"""Staff admin: Google-OAuth login (@rhpl.org) and CRUD over the catalog.

This is where RHPL staff manage the eResource databases after the one-time
migration off Polaris -- the new system of record. CSRF protection on every
POST is provided app-wide by Flask-WTF (see app.py).
"""
from __future__ import annotations

import logging
from functools import wraps

from flask import (Blueprint, abort, current_app, flash, redirect,
                   render_template, request, session, url_for)

from util import is_http_url, slugify, unique_slug

log = logging.getLogger("esources.admin")
bp = Blueprint("admin", __name__, url_prefix="/admin")


def _svc():
    return current_app.extensions["esources"]


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "admin_user" not in session:
            return redirect(url_for("admin.login"))
        return view(*args, **kwargs)
    return wrapped


# --- Authentication ---------------------------------------------------------

@bp.route("/login")
def login():
    if "admin_user" in session:
        return redirect(url_for("admin.index"))
    svc = _svc()
    redirect_uri = svc.config.public_base_url + url_for("admin.callback")
    return svc.oauth.google.authorize_redirect(redirect_uri)


@bp.route("/callback")
def callback():
    svc = _svc()
    try:
        token = svc.oauth.google.authorize_access_token()
    except Exception as exc:  # noqa: BLE001 — any OAuth failure -> login screen
        log.warning("OAuth callback failed: %s", exc)
        return render_template("admin/login.html",
                               error="Sign-in failed. Please try again."), 401

    userinfo = token.get("userinfo", {}) or {}
    email = (userinfo.get("email") or "").lower()
    domain = svc.config.admin_email_domain

    if not email.endswith("@" + domain):
        log.warning("admin login rejected for non-%s account: %s", domain, email)
        return render_template(
            "admin/login.html",
            error=f"Only @{domain} Google accounts may manage eResources."), 403

    session["admin_user"] = {"email": email, "name": userinfo.get("name", email)}
    log.info("admin login: %s", email)
    return redirect(url_for("admin.index"))


@bp.route("/logout")
def logout():
    user = session.pop("admin_user", {})
    log.info("admin logout: %s", user.get("email", "unknown"))
    return redirect(url_for("admin.login"))


# --- Listing ----------------------------------------------------------------

@bp.route("/")
@admin_required
def index():
    records = _svc().store.list_all()
    return render_template("admin/list.html", records=records,
                           user=session["admin_user"])


# --- Create / edit ----------------------------------------------------------

def _selected_categories(record: dict | None) -> list[str]:
    """Names already attached to a record, in alphabetical order."""
    if not record:
        return []
    names: list[str] = []
    seen = set()
    for c in record.get("categories") or []:
        name = (c.get("name") or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        names.append(name)
    return sorted(names, key=str.lower)


def _blocked_codes_text(record: dict | None) -> str:
    if not record:
        return ""
    return ", ".join(str(c) for c in (record.get("blocked_patron_code_ids") or []))


def _launch_params_text(record: dict | None) -> str:
    """Decrypt launch_params for display in the edit form."""
    if not record or not record.get("launch_params"):
        return ""
    from crypto import CryptoError
    try:
        params = _svc().crypto.decrypt_params(record["launch_params"])
    except CryptoError as exc:
        log.warning("decrypt_params failed in admin form: %s", exc)
        return ""
    return "\n".join(params)


def _parse_categories(names: list[str]) -> list[dict]:
    """Names from the form -> [{name:str}, ...], trimmed and de-duped."""
    out: list[dict] = []
    seen = set()
    for raw in names or []:
        name = (raw or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append({"name": name})
    return out


def _parse_blocked_codes(raw: str) -> list[int]:
    """`1, 3, 7` -> [1, 3, 7]. Non-numeric tokens are dropped."""
    out: list[int] = []
    for chunk in (raw or "").replace("\n", ",").split(","):
        c = chunk.strip()
        if c.isdigit():
            out.append(int(c))
    return out


def _parse_launch_params(raw: str) -> list[str]:
    """One key=value per line; blanks dropped."""
    return [line.strip() for line in (raw or "").splitlines() if line.strip()]


def _parse_int(raw: str, default: int) -> int:
    s = (raw or "").strip()
    try:
        return int(s)
    except ValueError:
        return default


def _parse_form(form, *, existing: dict | None, taken_slugs: set):
    """Build a record dict from the admin form. Returns (data, error_message).

    Launch-params handling: blank textarea leaves the saved ciphertext
    untouched on edit; checking "clear_launch_params" wipes it.
    """
    name = (form.get("name") or "").strip()
    if not name:
        return None, "Name is required."

    destination_url = (form.get("destination_url") or "").strip()
    if not is_http_url(destination_url):
        return None, "Destination URL must start with http:// or https://"

    slug = slugify(form.get("slug") or "") or slugify(name)
    if not slug:
        return None, "Could not derive a URL slug from that name."
    current_slug = (existing or {}).get("slug")
    if slug != current_slug and slug in taken_slugs:
        slug = unique_slug(slug, taken_slugs)

    raw_legacy = (form.get("legacy_entry_id") or "").strip()
    legacy_entry_id = int(raw_legacy) if raw_legacy.isdigit() else None

    data = {
        "name": name,
        "slug": slug,
        "legacy_entry_id": legacy_entry_id,
        "destination_url": destination_url,
        "in_house_access": _parse_int(form.get("in_house_access"), 3),
        "remote_access": _parse_int(form.get("remote_access"), 2),
        "transfer_type": _parse_int(form.get("transfer_type"), 2),
        "categories": _parse_categories(form.getlist("category")),
        "blocked_patron_code_ids": _parse_blocked_codes(
            form.get("blocked_patron_code_ids_text") or ""),
        "description": (form.get("description") or "").strip(),
        "message": (form.get("message") or "").strip(),
        "enabled": form.get("enabled") == "on",
    }

    # Launch params.
    svc = _svc()
    new_params_text = form.get("launch_params_text") or ""
    if form.get("clear_launch_params") == "on":
        data["launch_params"] = ""
    elif new_params_text.strip():
        params = _parse_launch_params(new_params_text)
        data["launch_params"] = svc.crypto.encrypt_params(params)
    elif existing is None:
        data["launch_params"] = ""
    # else: omit -> store.update keeps the existing ciphertext.

    return data, None


def _known_category_names() -> list[str]:
    """Distinct category names across the catalog, alphabetised."""
    seen = set()
    for rec in _svc().store.list_all():
        for c in rec.get("categories") or []:
            name = (c.get("name") or "").strip()
            if name:
                seen.add(name)
    return sorted(seen, key=str.lower)


def _render_edit(record, doc_id, *, form_source=None, status=200):
    """Render the edit form, deriving the text-mirror fields."""
    if form_source is None:
        selected = _selected_categories(record)
        blocked = _blocked_codes_text(record)
        launch_params = _launch_params_text(record)
    else:
        selected = list(form_source.getlist("category"))
        blocked = form_source.get("blocked_patron_code_ids_text") or ""
        launch_params = form_source.get("launch_params_text") or ""
    return render_template(
        "admin/edit.html",
        record=record, doc_id=doc_id,
        selected_categories=selected,
        blocked_codes_text=blocked,
        launch_params_text=launch_params,
        known_category_names=_known_category_names(),
        user=session["admin_user"]), status


@bp.route("/new", methods=["GET", "POST"])
@admin_required
def new():
    svc = _svc()
    if request.method == "GET":
        return _render_edit(None, None)

    data, error = _parse_form(request.form, existing=None,
                              taken_slugs=svc.store.all_slugs())
    if error:
        flash(error, "error")
        return _render_edit(request.form, None, form_source=request.form, status=400)

    doc_id = svc.store.create(data)
    log.info("admin %s created %s (%s)", session["admin_user"]["email"], doc_id, data["slug"])
    flash(f"Added “{data['name']}”.", "success")
    return redirect(url_for("admin.index"))


@bp.route("/<doc_id>/edit", methods=["GET", "POST"])
@admin_required
def edit(doc_id):
    svc = _svc()
    record = svc.store.get(doc_id)
    if record is None:
        abort(404)

    if request.method == "GET":
        return _render_edit(record, doc_id)

    data, error = _parse_form(request.form, existing=record,
                              taken_slugs=svc.store.all_slugs())
    if error:
        flash(error, "error")
        return _render_edit(record, doc_id, form_source=request.form, status=400)

    svc.store.update(doc_id, data)
    log.info("admin %s edited %s (%s)", session["admin_user"]["email"], doc_id, data["slug"])
    flash(f"Saved changes to “{data['name']}”.", "success")
    return redirect(url_for("admin.index"))


@bp.route("/<doc_id>/toggle", methods=["POST"])
@admin_required
def toggle(doc_id):
    svc = _svc()
    record = svc.store.get(doc_id)
    if record is None:
        abort(404)
    new_state = not record.get("enabled", True)
    svc.store.update(doc_id, {"enabled": new_state})
    log.info("admin %s toggled %s -> enabled=%s",
             session["admin_user"]["email"], doc_id, new_state)
    flash(f"“{record['name']}” is now "
          f"{'visible' if new_state else 'hidden'}.", "success")
    return redirect(url_for("admin.index"))


# --- Category management ----------------------------------------------------

def _category_counts() -> list[tuple[str, int]]:
    """Distinct category names with their record counts (alphabetical)."""
    counts: dict[str, int] = {}
    for rec in _svc().store.list_all():
        for c in rec.get("categories") or []:
            name = (c.get("name") or "").strip()
            if name:
                counts[name] = counts.get(name, 0) + 1
    return sorted(counts.items(), key=lambda kv: kv[0].lower())


def _rename_category(old: str, new: str) -> int:
    """Replace every occurrence of `old` with `new` across records.

    Returns the number of records touched. De-duplicates when a record
    already has `new` alongside `old`.
    """
    svc = _svc()
    old_lc = old.strip().lower()
    new_name = new.strip()
    touched = 0
    for rec in svc.store.list_all():
        cats = rec.get("categories") or []
        out: list[dict] = []
        seen = set()
        changed = False
        for c in cats:
            n = (c.get("name") or "").strip()
            if not n:
                continue
            if n.lower() == old_lc:
                n = new_name
                changed = True
            if n.lower() in seen:
                changed = True  # collapsed a duplicate
                continue
            seen.add(n.lower())
            out.append({"name": n})
        if changed:
            svc.store.update(rec["id"], {"categories": out})
            touched += 1
    return touched


def _delete_category(name: str) -> int:
    """Remove `name` from every record's categories. Returns records touched."""
    svc = _svc()
    target = name.strip().lower()
    touched = 0
    for rec in svc.store.list_all():
        cats = rec.get("categories") or []
        kept = [c for c in cats
                if (c.get("name") or "").strip().lower() != target]
        if len(kept) != len(cats):
            svc.store.update(rec["id"], {"categories": kept})
            touched += 1
    return touched


@bp.route("/categories")
@admin_required
def categories():
    return render_template(
        "admin/categories.html",
        categories=_category_counts(),
        user=session["admin_user"],
    )


@bp.route("/categories/rename", methods=["POST"])
@admin_required
def categories_rename():
    old = (request.form.get("old") or "").strip()
    new = (request.form.get("new") or "").strip()
    if not old or not new:
        flash("Both the old and new category names are required.", "error")
        return redirect(url_for("admin.categories"))
    if old.lower() == new.lower():
        flash("New name matches the old name — nothing to do.", "error")
        return redirect(url_for("admin.categories"))
    touched = _rename_category(old, new)
    log.info("admin %s renamed category %r -> %r (%d records)",
             session["admin_user"]["email"], old, new, touched)
    flash(f"Renamed “{old}” to “{new}” across {touched} record"
          f"{'s' if touched != 1 else ''}.", "success")
    return redirect(url_for("admin.categories"))


@bp.route("/categories/delete", methods=["POST"])
@admin_required
def categories_delete():
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Missing category name.", "error")
        return redirect(url_for("admin.categories"))
    touched = _delete_category(name)
    log.info("admin %s deleted category %r (%d records)",
             session["admin_user"]["email"], name, touched)
    flash(f"Removed “{name}” from {touched} record"
          f"{'s' if touched != 1 else ''}.", "success")
    return redirect(url_for("admin.categories"))


# --- Per-record actions -----------------------------------------------------

@bp.route("/<doc_id>/delete", methods=["POST"])
@admin_required
def delete(doc_id):
    svc = _svc()
    record = svc.store.get(doc_id)
    if record is None:
        abort(404)
    svc.store.delete(doc_id)
    log.info("admin %s deleted %s (%s)",
             session["admin_user"]["email"], doc_id, record.get("slug"))
    flash(f"Deleted “{record['name']}”.", "success")
    return redirect(url_for("admin.index"))
