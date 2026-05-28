"""pytest bootstrap.

Prefers an installed `esources` package (run `pip install -e .` after
cloning), but falls back to inserting `src/` on sys.path so a casual
`pytest` invocation works without a prior install.
"""
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_REPO_ROOT, "src")

try:
    import esources  # noqa: F401  — works if `pip install -e .` was done
except ImportError:
    if _SRC not in sys.path:
        sys.path.insert(0, _SRC)
