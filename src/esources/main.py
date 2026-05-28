"""RHPL eResources service — Flask application factory.

Replaces the legacy Polaris classic-PAC eSource feature. Runs as a container
on Cloud Run, behind Firebase Hosting at https://your-eresources-domain.org.

  - public blueprint  : patron listing + the IP / library-card access gateway
  - admin blueprint   : Google-OAuth (@rhpl.org) staff CRUD over the catalog

`app` at module scope is what gunicorn serves (see Dockerfile).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from authlib.integrations.flask_client import OAuth
from flask import Flask, render_template
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import Config, load_config
from .crypto import VendorCrypto
from .papi_client import PapiClient
from .ratelimit import RateLimiter
from .store import Store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("esources")

csrf = CSRFProtect()


@dataclass
class Services:
    """Everything the views need, built once at startup and stashed on the app."""

    config: Config
    store: Store
    papi: PapiClient
    crypto: VendorCrypto
    ratelimiter: RateLimiter
    oauth: OAuth


def create_app(config: Config | None = None) -> Flask:
    cfg = config or load_config()
    import os
    _REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    app = Flask(
        __name__,
        template_folder=os.path.join(_REPO_ROOT, "templates"),
        static_folder=os.path.join(_REPO_ROOT, "static"),
    )

    # --- Trust exactly TRUSTED_PROXY_HOPS proxies for X-Forwarded-* ---------
    # x_for drives request.remote_addr (the on-campus check). Verify the hop
    # count with /whoami before relying on the on-campus bypass.
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=cfg.trusted_proxy_hops,
        x_proto=1,
        x_host=1,
    )

    # --- Session / cookie security -----------------------------------------
    app.secret_key = cfg.secret_key
    app.permanent_session_lifetime = timedelta(minutes=cfg.session_minutes)
    app.config.update(
        # Firebase Hosting strips Cookie/Set-Cookie headers from CDN-proxied
        # requests for cacheability -- with one exception: the cookie named
        # exactly "__session" is allowed through. Renaming Flask's session
        # cookie to that is the documented workaround. See:
        # https://firebase.google.com/docs/hosting/manage-cache#using_cookies
        SESSION_COOKIE_NAME="__session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=cfg.public_base_url.startswith("https"),
        PREFERRED_URL_SCHEME="https" if cfg.public_base_url.startswith("https") else "http",
        WTF_CSRF_TIME_LIMIT=None,  # tie CSRF token validity to the session
    )

    csrf.init_app(app)

    # --- Shared services ----------------------------------------------------
    oauth = OAuth(app)
    oauth.register(
        name="google",
        client_id=cfg.google_client_id,
        client_secret=cfg.google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

    services = Services(
        config=cfg,
        store=Store(project=cfg.gcp_project),
        papi=PapiClient(
            base_url=cfg.papi_base_url,
            lang_id=cfg.papi_lang_id,
            app_id=cfg.papi_app_id,
            org_id=cfg.papi_org_id,
            api_access_id=cfg.papi_api_access_id,
            api_secret=cfg.papi_api_secret,
        ),
        crypto=VendorCrypto(cfg.fernet_key),
        ratelimiter=None,  # set below — needs the store's Firestore client
        oauth=oauth,
    )
    services.ratelimiter = RateLimiter(
        client=services.store.db,
        max_attempts=cfg.login_rate_max,
        window_minutes=cfg.login_rate_window_min,
    )
    app.extensions["esources"] = services

    # --- Blueprints ---------------------------------------------------------
    from routes.api import bp as api_bp
    from routes.public import bp as public_bp
    from routes.admin import bp as admin_bp

    # The JSON API is read-only and consumed by cross-origin clients
    # (Wix Velo, etc.) -- exempt it from CSRF; it has no state-changing routes.
    csrf.exempt(api_bp)

    app.register_blueprint(api_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)

    # --- Error handlers -----------------------------------------------------
    @app.errorhandler(404)
    def _not_found(_err):
        return render_template("error.html", title="Not found",
                               message="That page or resource could not be found."), 404

    @app.errorhandler(500)
    def _server_error(_err):
        log.exception("unhandled error")
        return render_template("error.html", title="Something went wrong",
                               message="Please try again in a moment."), 500

    log.info("eResources service started (project=%s, base=%s, proxy_hops=%d)",
             cfg.gcp_project, cfg.public_base_url, cfg.trusted_proxy_hops)
    return app


# gunicorn entrypoint: `gunicorn app:app`
app = create_app()


if __name__ == "__main__":
    # Local dev only. Production runs under gunicorn (see Dockerfile).
    app.run(host="127.0.0.1", port=8080, debug=True)
