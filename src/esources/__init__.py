"""RHPL eResources service.

The Flask application factory and module-level `app` instance live in
`esources.main`. For gunicorn:

    gunicorn esources.main:app

This package's __init__ deliberately does NOT eagerly import `main`,
because doing so would call `create_app()` (and therefore `load_config()`)
at first `import esources.<anything>` — which makes unit tests that only
need pure modules (gateway, util, crypto) fail without env vars.
Submodules should be imported directly:

    from esources.gateway import decide_access
    from esources.main import create_app
"""
