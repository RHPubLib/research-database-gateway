"""One-shot: remove the "Alphabetical List" category from every record.

It duplicates the sidebar's "All" filter and was just adding visual noise
on the embed's card chips. Run dry-run by default; pass --apply to write.
"""
from __future__ import annotations
import os
import sys

# Minimal .env loader (avoids extra dep): just pulls GCP_PROJECT.
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

TARGET_NAME = "alphabetical list"  # matched case-insensitively


def main():
    project = os.environ["GCP_PROJECT"]
    dry_run = "--apply" not in sys.argv
    store = Store(project=project)

    touched = []
    for rec in store.list_all():
        cats = rec.get("categories") or []
        kept = [
            c for c in cats
            if (c.get("name") or "").strip().lower() != TARGET_NAME
        ]
        if len(kept) == len(cats):
            continue
        touched.append((rec["id"], rec.get("name"), len(cats), len(kept)))
        if not dry_run:
            store.update(rec["id"], {"categories": kept})

    print(f"{'APPLY' if not dry_run else 'DRY-RUN'} — project={project}")
    print(f"Records affected: {len(touched)}")
    for doc_id, name, before, after in touched:
        print(f"  {doc_id}  {name}  ({before} -> {after} categories)")
    if dry_run:
        print("\nRe-run with --apply to write.")


if __name__ == "__main__":
    main()
