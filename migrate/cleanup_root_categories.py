"""One-time cleanup: strip ROOT category placements from live Firestore records.

ROOT is a Polaris structural node, not a patron-facing category. The first
import (2026-05-23) included it because the importer treated ROOT like any
other category name. The import has since been patched to drop ROOT at load
time (see _load_categories in import_extract.py); this script fixes the
records already in Firestore.

Effects:
  - Records that have ROOT plus other categories: ROOT placement removed,
    other categories unchanged.
  - Records whose ONLY placement was ROOT: categories list becomes empty.
    The patron listing falls back to a "Databases" default for empty-cat
    records (see routes/public.py listing()).

Usage:
    python3 migrate/cleanup_root_categories.py             # dry-run (default)
    python3 migrate/cleanup_root_categories.py --apply     # write changes
"""
from __future__ import annotations

import argparse
import os
import sys

from google.cloud import firestore


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", default=os.environ.get("GCP_PROJECT", "your-library-esources"))
    ap.add_argument("--apply", action="store_true",
                    help="actually write the changes (default: dry-run)")
    args = ap.parse_args()

    db = firestore.Client(project=args.project)
    col = db.collection("esources")

    affected = []
    for snap in col.stream():
        data = snap.to_dict() or {}
        cats = data.get("categories") or []
        has_root = any((c.get("name") or "").strip().upper() == "ROOT" for c in cats)
        if not has_root:
            continue
        new_cats = [c for c in cats if (c.get("name") or "").strip().upper() != "ROOT"]
        affected.append((snap.id, data.get("name", ""), cats, new_cats))

    if not affected:
        print("nothing to clean up -- no records have ROOT in categories")
        return 0

    print(f"found {len(affected)} record(s) with ROOT placements:")
    for doc_id, name, before, after in affected:
        print(f"  {doc_id}  {name!r}")
        print(f"    before: {[c.get('name') for c in before]}")
        print(f"    after:  {[c.get('name') for c in after]}")

    if not args.apply:
        print("\n(dry-run) re-run with --apply to write changes")
        return 0

    print("\napplying writes…")
    for doc_id, _, _, after in affected:
        col.document(doc_id).update({
            "categories": after,
            "updated_at": firestore.SERVER_TIMESTAMP,
        })
    print(f"  wrote {len(affected)} record(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
