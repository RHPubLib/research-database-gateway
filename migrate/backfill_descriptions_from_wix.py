"""One-off: backfill 15 missing descriptions from the Wix research-databases
page on www.rhpl.org. Each entry is matched by legacy_entry_id (Polaris
Target=). Run from the repo root with the .venv active and
GOOGLE_APPLICATION_CREDENTIALS pointed at a Firestore-writable principal.
"""
from __future__ import annotations

import sys

from store import Store

BACKFILLS: list[tuple[int, str]] = [
    (826, "Discover new crafts with more than 1,000 award-winning video classes taught by design experts and artists."),
    (830, "Search for service, repair, and recall information for domestic and imported vehicles from the Original Equipment Manufacturers (OEM)."),
    (834, "Find comprehensive travel information, including more than 200 World City Travel Guides."),
    (843, "Find over 700 comprehensive, interactive practice tests and courses for academic and vocational certification and licensing."),
    (862, "Research company reports, stocks, mutual funds, and other securities."),
    (965, "Browse an online collection of animated, talking picture books."),
    (967, "Find information on 100,000+ foundations, corporate giving programs, and grant-making public charities in the U.S. In-Library Use Only."),
    (977, "Access The Wall Street Journal from anywhere."),
    (991, "A fun and free way to learn 315 languages with personalized courses, audio libraries, movies, and chats."),
    (992, "Learn 163 languages with Bluebird, the largest audiobook library in the world with 12 million prerecorded lessons."),
    (998, "Reviews, recommendations, read-alikes, author bios and interviews, resources for book clubs, and more."),
    (999, "Newspapers from 1690 to today, from across the U.S. and beyond."),
    (1000, "An essential collection of genealogical and historical sources with coverage dating back to the 1700s."),
    (1006, "Learn a new skill by choosing from over 25,000+ online video courses."),
    (1007, "Access thousands of printable worksheets, lesson ideas, and activities for all grades in and outside the classroom."),
]


def main(project: str = "your-library-esources", dry_run: bool = False) -> int:
    store = Store(project=project)
    updated = 0
    skipped = 0
    for legacy_id, desc in BACKFILLS:
        rec = store.get_by_legacy_id(legacy_id)
        if rec is None:
            print(f"  [{legacy_id}] NOT FOUND in Firestore -- skipping")
            skipped += 1
            continue
        current = (rec.get("description") or "").strip()
        if current:
            print(f"  [{legacy_id}] {rec['name']!r} already has a description -- skipping")
            skipped += 1
            continue
        action = "WOULD UPDATE" if dry_run else "UPDATING"
        print(f"  [{legacy_id}] {action} {rec['name']!r}")
        print(f"       -> {desc}")
        if not dry_run:
            store.update(rec["id"], {"description": desc})
        updated += 1
    print(f"\nDone. {updated} updated, {skipped} skipped.")
    return 0


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    sys.exit(main(dry_run=dry))
