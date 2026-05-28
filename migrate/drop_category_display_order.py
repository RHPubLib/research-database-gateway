"""One-shot: collapse each record's `categories` entries to just {name}.

Polaris's display_order field was confusing in the admin UI: it conflated
per-record item ordering with global sidebar ordering, and the sidebar
already used "lowest across records wins" so the per-record number was
mostly ignored. We now sort categories alphabetically everywhere, so the
field is dead weight. This script strips it from every record.
"""
from __future__ import annotations
import os
import sys

_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from store import Store  # noqa: E402


def main():
    project = os.environ["GCP_PROJECT"]
    dry_run = "--apply" not in sys.argv
    store = Store(project=project)

    touched = []
    for rec in store.list_all():
        cats = rec.get("categories") or []
        new_cats = []
        seen = set()
        for c in cats:
            name = (c.get("name") or "").strip()
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            new_cats.append({"name": name})
        if new_cats == cats:
            continue
        touched.append((rec["id"], rec.get("name"), len(cats), len(new_cats)))
        if not dry_run:
            store.update(rec["id"], {"categories": new_cats})

    print(f"{'APPLY' if not dry_run else 'DRY-RUN'} — project={project}")
    print(f"Records touched: {len(touched)}")
    for doc_id, name, before, after in touched[:5]:
        print(f"  {doc_id}  {name}  ({before} -> {after} entries)")
    if len(touched) > 5:
        print(f"  ... ({len(touched) - 5} more)")
    if dry_run:
        print("\nRe-run with --apply to write.")


if __name__ == "__main__":
    main()
