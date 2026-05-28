#!/usr/bin/env python3
"""eResources migration -- STEP 3: import the Polaris extract into Firestore.

Reads the three CSVs produced by 02_extract_esources.sql:
    esources.csv     -- one row per (database, category placement);
                        the SAME EntryID appears N times if cross-listed
    categories.csv   -- parent_entry_id -> category_name
    parameters.csv   -- one row per launch parameter (key=value)

Builds one Firestore document per unique database (deduplicating the
cross-listings into a `categories: list[{name, display_order}]` field),
encrypts the launch parameters, and upserts the `esources` collection.
Run once at cutover; safe to re-run (upserts by legacy_entry_id).

Notes on the source CSVs (see migrate/02_extract_esources.sql header for
the full rationale):
    * SSMS exports the `launch_parameters` column with embedded CHAR(10)
      newlines flattened to spaces -- it is UNRELIABLE and we ignore it.
      parameters.csv (Query C) is the authoritative source.
    * Categories whose name ends in " Old" are legacy Polaris cleanup;
      they are dropped here at load time so the filter is visible.

Usage
-----
    # preview only -- pure CSV parse, no GCP / Fernet needed:
    python migrate/import_extract.py --dry-run

    # real import (needs Application Default Credentials + FERNET_KEY):
    gcloud auth application-default login
    export GCP_PROJECT=your-library-esources
    export FERNET_KEY=...
    python migrate/import_extract.py

Default CSV paths are migrate/extract/{esources,categories,parameters}.csv.
Export the CSVs as UTF-8. If SSMS gave you UTF-16:
    iconv -f UTF-16 -t UTF-8 in.csv > esources.csv
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict
from pathlib import Path

# Allow `import util` / `import store` when run from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from util import unique_slug  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_ESOURCES = HERE / "extract" / "esources.csv"
DEFAULT_CATEGORIES = HERE / "extract" / "categories.csv"
DEFAULT_PARAMETERS = HERE / "extract" / "parameters.csv"


def _clean(value: str | None) -> str:
    """Trim, and treat the SQL-export literal 'NULL' as empty."""
    v = (value or "").strip()
    return "" if v.upper() == "NULL" else v


def _read_csv(path: Path) -> list[dict]:
    """Read a CSV with a header row; lowercase the header keys."""
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = []
        for raw in reader:
            rows.append({(k or "").strip().lower(): v for k, v in raw.items()})
        return rows


def _load_categories(path: Path) -> tuple[dict, set]:
    """Returns (live_categories, old_parent_ids).

    live_categories: parent_entry_id -> category_name (only non-"Old",
        non-ROOT categories)
    old_parent_ids: set of parent_entry_ids for categories whose names end
        in " Old". An ETarget whose only placements are in old_parent_ids is
        a ghost (legacy Polaris record retired from the live catalog) and
        gets dropped by build_records.

    "ROOT" categories are silently dropped here -- they are Polaris's
    top-level structural nodes (parent_entry_id 5 and 6 in our extract)
    that the staff client uses to anchor the category tree. They should
    never reach the patron-facing listing. Records whose only placement
    is ROOT fall through to the "no categories" default ("Databases").
    """
    if not path.is_file():
        print(f"  note: no categories file at {path} -- categories left blank")
        return {}, set()
    mapping = {}
    old_pids: set[int] = set()
    root_dropped = 0
    for row in _read_csv(path):
        pid = _clean(row.get("parent_entry_id"))
        name = _clean(row.get("category_name"))
        if not pid.isdigit() or not name:
            continue
        if name.rstrip().lower().endswith(" old"):
            old_pids.add(int(pid))
            continue
        if name.strip().upper() == "ROOT":
            root_dropped += 1
            continue
        mapping[int(pid)] = name
    if old_pids:
        print(f"  marked {len(old_pids)} legacy 'Old' categories as ghost-only")
    if root_dropped:
        print(f"  dropped {root_dropped} 'ROOT' structural categories")
    return mapping, old_pids


def _load_parameters(path: Path) -> dict[int, list[str]]:
    """legacy_entry_id -> list of "key=value" launch-parameter strings."""
    if not path.is_file():
        print(f"  note: no parameters file at {path} -- no launch params loaded")
        return {}
    out: dict[int, list[str]] = defaultdict(list)
    for row in _read_csv(path):
        eid = _clean(row.get("legacy_entry_id"))
        param = (row.get("parameter") or "").strip()
        if eid.isdigit() and param:
            out[int(eid)].append(param)
    return dict(out)


def _parse_blocked_codes(raw: str) -> list[int]:
    """`3,8,19` -> [3, 8, 19]. Skips non-numeric / NULL.

    These are the PatronCodeIDs to BLOCK (Polaris UI: "patron codes to
    restrict"). The CSV column header is still `allowed_patron_code_ids`
    for backwards compat with existing exports; the semantic is block-list.
    """
    if not raw or raw.upper() == "NULL":
        return []
    out: list[int] = []
    for c in raw.split(","):
        c = c.strip()
        if c.isdigit():
            out.append(int(c))
    return out


def _is_valid_url(url: str) -> bool:
    """Reject ETarget URLs that lack a scheme. EntryID 824 ('Ancestry.com')
    stored its URL as a bare hostname -- a smell of legacy Polaris records
    pre-dating the scheme-required convention. Live records all have
    http:// or https://."""
    u = (url or "").strip().lower()
    return u.startswith("http://") or u.startswith("https://")


def _parse_int_or(default: int, raw: str | None) -> int:
    v = _clean(raw)
    try:
        return int(v) if v else default
    except ValueError:
        return default


def build_records(esources_csv: Path, categories_csv: Path,
                  parameters_csv: Path) -> tuple[list, list]:
    """Return (records, skipped). One record per UNIQUE legacy_entry_id.

    Two ghost filters drop legacy Polaris records that the classic PAC
    wasn't surfacing:
      * malformed URL (no http:// or https:// scheme)
      * every category placement is in an "Old" category (or none at all)
    """
    categories, old_pids = _load_categories(categories_csv)
    parameters = _load_parameters(parameters_csv)

    # First pass: group esources.csv rows by legacy_entry_id, accumulating
    # both live category placements (kept) and "Old" placements (used only
    # to decide ghost status).
    by_eid: dict[int, dict] = {}
    skipped: list[dict] = []
    for row in _read_csv(esources_csv):
        legacy_raw = _clean(row.get("legacy_entry_id"))
        name = _clean(row.get("name"))
        url = _clean(row.get("url"))

        if not url or not name or not legacy_raw.isdigit():
            skipped.append({"legacy_entry_id": legacy_raw, "name": name,
                            "reason": "missing legacy_entry_id, name, or URL"})
            continue
        if not _is_valid_url(url):
            skipped.append({"legacy_entry_id": legacy_raw, "name": name,
                            "reason": f"malformed URL (no scheme): {url!r}"})
            continue
        eid = int(legacy_raw)

        # Resolve this row's category placement.
        parent_raw = _clean(row.get("parent_entry_id"))
        order_raw = _clean(row.get("display_order"))
        try:
            display_order = int(float(order_raw)) if order_raw else 0
        except ValueError:
            display_order = 0
        category_name = ""
        is_old_placement = False
        if parent_raw.isdigit():
            pid = int(parent_raw)
            category_name = categories.get(pid, "")
            if not category_name and pid in old_pids:
                is_old_placement = True

        if eid not in by_eid:
            by_eid[eid] = {
                "legacy_entry_id": eid,
                "name": name,
                "destination_url": url,
                "in_house_access": _parse_int_or(3, row.get("in_house_access")),
                "remote_access": _parse_int_or(2, row.get("remote_access")),
                "transfer_type": _parse_int_or(2, row.get("transfer_type")),
                "blocked_patron_code_ids": _parse_blocked_codes(
                    # Newer SQL exports use the correct column name; legacy
                    # exports (pre-2026-05-23) wrote it as "allowed_...".
                    row.get("blocked_patron_code_ids")
                    or row.get("allowed_patron_code_ids") or ""),
                "description": _clean(row.get("description")),
                "message": _clean(row.get("message")),
                "_categories": [],     # live placements (kept)
                "_old_only": True,     # flipped false on first live placement
                "enabled": True,
            }
        if category_name:
            existing = {c["name"] for c in by_eid[eid]["_categories"]}
            if category_name not in existing:
                by_eid[eid]["_categories"].append({
                    "name": category_name,
                    "display_order": display_order,
                })
            by_eid[eid]["_old_only"] = False
        elif not is_old_placement:
            # Unknown / uncategorised placement -- treat as "not Old-only".
            by_eid[eid]["_old_only"] = False

    # Second pass: drop ghosts, then build the final records.
    records: list[dict] = []
    taken_slugs: set[str] = set()
    for eid, rec in sorted(by_eid.items()):
        if rec.pop("_old_only"):
            skipped.append({
                "legacy_entry_id": eid, "name": rec["name"],
                "reason": "ghost: only in 'Old' categories",
            })
            continue
        rec["categories"] = sorted(
            rec.pop("_categories"),
            key=lambda c: (c["display_order"], c["name"].lower()),
        )
        slug = unique_slug(rec["name"], taken_slugs)
        taken_slugs.add(slug)
        rec["slug"] = slug
        rec["_launch_params_plain"] = parameters.get(eid, [])
        records.append(rec)
    return records, skipped


def main() -> int:
    ap = argparse.ArgumentParser(description="Import the Polaris eSource extract into Firestore.")
    ap.add_argument("--esources-csv", type=Path, default=DEFAULT_ESOURCES)
    ap.add_argument("--categories-csv", type=Path, default=DEFAULT_CATEGORIES)
    ap.add_argument("--parameters-csv", type=Path, default=DEFAULT_PARAMETERS)
    ap.add_argument("--project", default=os.environ.get("GCP_PROJECT", ""))
    ap.add_argument("--dry-run", action="store_true",
                    help="parse the CSVs and report; write nothing")
    args = ap.parse_args()

    for required in (args.esources_csv,):
        if not required.is_file():
            print(f"ERROR: extract not found: {required}", file=sys.stderr)
            print("Run 02_extract_esources.sql and save the result as that file.",
                  file=sys.stderr)
            return 1

    records, skipped = build_records(
        args.esources_csv, args.categories_csv, args.parameters_csv)
    with_params = sum(1 for r in records if r["_launch_params_plain"])
    with_codes = sum(1 for r in records if r["blocked_patron_code_ids"])

    print(f"\nParsed {len(records)} UNIQUE databases (from {args.esources_csv.name})")
    print(f"  {with_params:4d} carry launch parameters (vendor-credential-bearing)")
    print(f"  {with_codes:4d} have a block-list of PatronCodeIDs")
    print(f"  {len(skipped):4d} skipped (ghost or malformed)")
    for s in skipped:
        print(f"       - skipped EntryID={s['legacy_entry_id']!r} {s['name']!r}: {s['reason']}")

    if args.dry_run:
        print("\n--dry-run: nothing written. Sample of what would be imported:")
        for r in records[:5]:
            cats = ", ".join(f"{c['name']}({c['display_order']})" for c in r["categories"])
            print(f"  [{r['legacy_entry_id']}] {r['name']}  ->  /go/{r['slug']}")
            print(f"     categories: {cats or '(none)'}")
            print(f"     in_house={r['in_house_access']} remote={r['remote_access']} "
                  f"params={len(r['_launch_params_plain'])} "
                  f"blocked_codes={r['blocked_patron_code_ids'] or 'none'}")
        if len(records) > 5:
            print(f"  ... and {len(records) - 5} more")
        return 0

    # --- real import ---
    if not args.project:
        print("ERROR: set GCP_PROJECT (or pass --project)", file=sys.stderr)
        return 1
    fernet_key = os.environ.get("FERNET_KEY", "")
    if not fernet_key:
        print("ERROR: set FERNET_KEY -- the same key Cloud Run uses.", file=sys.stderr)
        return 1

    from crypto import VendorCrypto
    from store import Store

    crypto = VendorCrypto(fernet_key)
    store = Store(project=args.project)

    created = updated = 0
    for r in records:
        data = {k: v for k, v in r.items() if not k.startswith("_")}
        data["launch_params"] = crypto.encrypt_params(r["_launch_params_plain"])

        existing = store.get_by_legacy_id(data["legacy_entry_id"])
        if existing:
            data["slug"] = existing["slug"]   # keep the live slug stable
            store.update(existing["id"], data)
            updated += 1
        else:
            store.create(data)
            created += 1

    print(f"\nImport complete: {created} created, {updated} updated.")
    print("Next: spot-check the 7 entries with block-lists in the admin UI ")
    print("      (PressReader, Pronunciator, 3x Makerspace, Udemy, "
          "Scholastic Teachables). Each should block non-RHPL patron codes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
