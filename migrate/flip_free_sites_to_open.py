"""One-shot: flip remote_access from 3 (IP-only) to 1 (Open) for the 16
free-public sites that Polaris had defaulted to IP-only. See CLAUDE.md
session 2026-05-27 for the rationale.
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

FREE_LEGACY_IDS = [
    949,  # Chronicling America
    950,  # Digital Michigan Newspapers
    877,  # Digital Public Library of America
    931,  # Europeana
    876,  # Dead Fred Genealogy Photo Archive
    878,  # Find A Grave
    880,  # Genealogy Research at the Library of Michigan
    924,  # MedlinePlus
    846,  # Michigan Authors and Illustrators
    943,  # Michigan Legal Help
    944,  # Michigan Memories
    881,  # Michiganology
    883,  # Red Book (FamilySearch wiki)
    947,  # Remembering Rochester
    948,  # Rochester Hills Museum at Van Hoosen Farm
    884,  # VA Nationwide Gravesite Locator
]


def main():
    project = os.environ["GCP_PROJECT"]
    dry_run = "--apply" not in sys.argv
    store = Store(project=project)
    updated = []
    missing = []
    skipped = []
    for legacy_id in FREE_LEGACY_IDS:
        rec = store.get_by_legacy_id(legacy_id)
        if not rec:
            missing.append(legacy_id)
            continue
        if rec.get("remote_access") == 1:
            skipped.append((legacy_id, rec.get("name")))
            continue
        if not dry_run:
            store.update(rec["id"], {"remote_access": 1})
        updated.append((legacy_id, rec.get("name"), rec.get("remote_access")))
    print(f"{'APPLY' if not dry_run else 'DRY-RUN'} — project={project}")
    print(f"Would update {len(updated)}:")
    for lid, name, old in updated:
        print(f"  {lid:>4}  remote_access {old} -> 1   {name}")
    if skipped:
        print(f"Already open ({len(skipped)}):")
        for lid, name in skipped:
            print(f"  {lid:>4}  {name}")
    if missing:
        print(f"NOT FOUND in Firestore: {missing}")
    if dry_run:
        print("\nRe-run with --apply to write.")


if __name__ == "__main__":
    main()
