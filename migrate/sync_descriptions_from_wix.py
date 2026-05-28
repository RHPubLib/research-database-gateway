"""One-off: mirror every description from the live Wix research-databases
page (www.rhpl.org/research-databases) into Firestore, overwriting the
existing description on each matching record. Matching is by legacy_entry_id
(the Polaris Target= value).

Wix is the staff-managed source of truth for blurbs today, so this script
realigns the new system to that source. Records present in Firestore but not
on Wix (e.g. internal-only "Makerspace Appointment") are left untouched.

Run from the repo root with the .venv active and an
application-default-credentials principal that can write to Firestore.

  PYTHONPATH=. .venv/bin/python migrate/sync_descriptions_from_wix.py --dry-run
  PYTHONPATH=. .venv/bin/python migrate/sync_descriptions_from_wix.py
"""
from __future__ import annotations

import html as htmllib
import re
import sys
import urllib.request

from store import Store

WIX_URL = "https://www.rhpl.org/research-databases"


def _strip(s: str) -> str:
    return htmllib.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def fetch_wix_descriptions() -> dict[int, str]:
    """Return {legacy_entry_id: description} parsed from the Wix page.

    Each database card on Wix shares a UUID across three sibling components:
    the Visit button (carries the Polaris Target=NNN URL), the title rich
    text (comp-mcdq8dj5__UUID), and the description rich text
    (comp-mcdq8dj75__UUID). We pair them via the UUID.
    """
    html = urllib.request.urlopen(WIX_URL).read().decode("utf-8", errors="replace")
    btn_re = re.compile(
        r'comp-mcdq8dj0__([a-f0-9-]+)[^>]*aria-disabled="false"><a [^>]*?Target=(\d+)'
    )
    out: dict[int, str] = {}
    for m in btn_re.finditer(html):
        uuid, target = m.group(1), int(m.group(2))
        dm = re.search(
            rf"comp-mcdq8dj75__{re.escape(uuid)}[^>]*>(.*?)</div><!--/\$-->",
            html,
            re.DOTALL,
        )
        if dm:
            out[target] = _strip(dm.group(1))
    return out


def main(project: str = "your-library-esources", dry_run: bool = False) -> int:
    descriptions = fetch_wix_descriptions()
    print(f"Parsed {len(descriptions)} descriptions from Wix.\n")
    store = Store(project=project)
    updated = unchanged = no_wix = empty_wix = 0
    for rec in store.list_all():
        legacy_id = rec.get("legacy_entry_id")
        wix_desc = descriptions.get(legacy_id)
        current = (rec.get("description") or "").strip()
        if wix_desc is None:
            print(f"  [{legacy_id}] {rec['name']!r} -- not on Wix, leaving alone")
            no_wix += 1
            continue
        if not wix_desc:
            print(f"  [{legacy_id}] {rec['name']!r} -- Wix description is empty, leaving alone")
            empty_wix += 1
            continue
        if current == wix_desc:
            unchanged += 1
            continue
        action = "WOULD UPDATE" if dry_run else "UPDATING"
        print(f"  [{legacy_id}] {action} {rec['name']!r}")
        print(f"       OLD: {current[:120]!r}")
        print(f"       NEW: {wix_desc[:120]!r}")
        if not dry_run:
            store.update(rec["id"], {"description": wix_desc})
        updated += 1
    print(
        f"\nDone. {updated} updated, {unchanged} already matched, "
        f"{no_wix} not on Wix, {empty_wix} blank on Wix."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(dry_run="--dry-run" in sys.argv))
