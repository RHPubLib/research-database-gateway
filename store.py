"""Firestore data access for the eResource catalog.

Single source of truth: the `esources` collection, one document per unique
database (Polaris's DWIEntries.EntryID). The dataset is tiny (~250 docs), so
list queries use a single equality filter (automatic single-field index) and
sort in Python -- no composite indexes to deploy.

Document fields
---------------
  legacy_entry_id        int    Polaris DWIEntries.EntryID. Stable external
                                key -- lets old `?Target=NNN` bookmarks be
                                re-pointed and lets the migration upsert
                                instead of duplicating.
  name                   str    Display name.
  slug                   str    URL-safe key used by /go/<slug>. Unique.
  destination_url        str    Base URL the patron is sent to (no query
                                params -- launch_params is the param source).
  launch_params          str    Fernet-encrypted JSON list of "key=value"
                                strings. Appended to destination_url as a
                                query string at redirect time. May contain
                                vendor credentials; never logged.
  in_house_access        int    1=open, 2=card-required, 3=IP-only.
                                Polaris's InHouseAccess enum.
  remote_access          int    1=open, 2=card-required, 3=blocked off-site.
                                Polaris's RemoteAccess enum.
  transfer_type          int    1 or 2 -- Polaris ESourceTransferTypeID;
                                currently informational, used to decide
                                future POST-style launches if needed.
  categories             list   List of {"name": str}. Databases can live
                                under multiple categories (Polaris cross-listed
                                ~half the catalog); the listing renders each
                                placement. Categories are sorted alphabetically
                                in both the patron listing and the embed.
  blocked_patron_code_ids list  List[int] of Polaris PatronCodeIDs that
                                are BLOCKED from access (Polaris UI label:
                                "patron codes to restrict"). Empty = no
                                restriction. Enforced only on card-authed
                                requests; in-library IP bypass mirrors
                                Polaris's InHouseAccess=3.
  description            str    Public blurb shown on the listing.
  message                str    Extra public note from Polaris's Message
                                attribute.
  enabled                bool   False hides it from the listing and 404s /go.
  created_at             ts     Server timestamp.
  updated_at             ts     Server timestamp.
"""
from __future__ import annotations

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

COLLECTION = "esources"

# Fields a record carries, with defaults, so create/update always write a
# complete, predictable document.
_DEFAULTS = {
    "legacy_entry_id": None,
    "name": "",
    "slug": "",
    "destination_url": "",
    "launch_params": "",
    "in_house_access": 3,
    "remote_access": 2,
    "transfer_type": 2,
    "categories": [],
    "blocked_patron_code_ids": [],
    "description": "",
    "message": "",
    "enabled": True,
}


def _to_record(doc) -> dict:
    """Firestore snapshot -> plain dict with its document id under `id`."""
    data = doc.to_dict() or {}
    rec = {**_DEFAULTS, **data}
    rec["id"] = doc.id
    return rec


def _primary_sort_key(rec: dict):
    """Sort key used for the admin list (single line per database)."""
    return (rec.get("name") or "").lower()


class Store:
    """Thin wrapper over the Firestore `esources` collection."""

    def __init__(self, project: str, client: firestore.Client | None = None):
        self._db = client or firestore.Client(project=project)

    @property
    def db(self) -> firestore.Client:
        return self._db

    def _col(self):
        return self._db.collection(COLLECTION)

    # --- reads ---------------------------------------------------------------

    def list_all(self) -> list:
        """Every record, enabled or not -- for the admin UI."""
        recs = [_to_record(d) for d in self._col().stream()]
        recs.sort(key=_primary_sort_key)
        return recs

    def list_enabled(self) -> list:
        """Enabled records only -- for the patron listing page."""
        q = self._col().where(filter=FieldFilter("enabled", "==", True))
        recs = [_to_record(d) for d in q.stream()]
        recs.sort(key=_primary_sort_key)
        return recs

    def get(self, doc_id: str) -> dict | None:
        snap = self._col().document(doc_id).get()
        return _to_record(snap) if snap.exists else None

    def get_by_slug(self, slug: str) -> dict | None:
        q = self._col().where(filter=FieldFilter("slug", "==", slug)).limit(1)
        for d in q.stream():
            return _to_record(d)
        return None

    def get_by_legacy_id(self, legacy_entry_id: int) -> dict | None:
        q = (
            self._col()
            .where(filter=FieldFilter("legacy_entry_id", "==", int(legacy_entry_id)))
            .limit(1)
        )
        for d in q.stream():
            return _to_record(d)
        return None

    def all_slugs(self) -> set:
        """All slugs in use -- for collision-free slug generation."""
        return {(_to_record(d).get("slug") or "") for d in self._col().stream()}

    # --- writes --------------------------------------------------------------

    def create(self, data: dict) -> str:
        """Insert a new record. Returns the new document id."""
        rec = {**_DEFAULTS, **{k: v for k, v in data.items() if k in _DEFAULTS}}
        rec["created_at"] = firestore.SERVER_TIMESTAMP
        rec["updated_at"] = firestore.SERVER_TIMESTAMP
        ref = self._col().document()
        ref.set(rec)
        return ref.id

    def update(self, doc_id: str, data: dict) -> None:
        """Patch an existing record. Only known fields are written."""
        rec = {k: v for k, v in data.items() if k in _DEFAULTS}
        rec["updated_at"] = firestore.SERVER_TIMESTAMP
        self._col().document(doc_id).update(rec)

    def delete(self, doc_id: str) -> None:
        self._col().document(doc_id).delete()
