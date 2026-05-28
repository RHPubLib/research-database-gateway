"""The eResource access decision -- kept as a pure function so it is unit
testable without Flask, Firestore, or PAPI.

Mirrors the legacy Polaris esources.aspx behaviour using Polaris's own
access enums (InHouseAccess / RemoteAccess), plus a blocked-patron-codes
list (Polaris UI: "patron codes to restrict") for resources that block
specific patron types -- typically non-RHPL types like Non-Resident,
MILibrary, Collection Agency, etc. The current live set is seven
resources (PressReader, the Makerspace pages, Pronunciator, Udemy,
Scholastic Teachables).

Access-enum values (1/2/3) come straight from Polaris; same meaning in
both InHouseAccess and RemoteAccess:
    1 = Open: anyone -- no card login required
    2 = Card-required: patron must log in with their library card
    3 = IP-only: granted by being on a library IP; cannot be reached
        from off-site by any means (no login form is offered)

Patron-code enforcement matches what Polaris actually did: it only kicks
in once we know the patron's PatronCodeID, i.e. after a card login. An
on-campus walk-in with InHouseAccess=3 gets through without a code check,
because IP-grant in Polaris carried no patron identity. (See
~/.claude/projects/-var-opt-your-library-esources/memory/open-questions.md for
the open policy question on Ancestry walk-ins.)
"""
from __future__ import annotations

# Decision outcomes returned by decide_access().
GRANT = "grant"                          # send the patron to the resource
LOGIN = "login"                          # show the library-card login form
DENY_OFFSITE = "deny_offsite"            # in-library only; login cannot help
DENY_PATRON_CODE = "deny_patron_code"    # logged in, but card type not eligible

# Access-enum constants -- single source of truth.
ACCESS_OPEN = 1
ACCESS_CARD = 2
ACCESS_IP_ONLY = 3


def decide_access(
    *,
    on_campus: bool,
    authed: bool,
    in_house_access: int,
    remote_access: int,
    patron_code_id: int | None = None,
    blocked_patron_code_ids: list | None = None,
) -> str:
    """Decide what to do with a patron requesting an eResource.

    Keyword-only so the call sites are self-documenting -- the boolean
    sequence is the same kind of trap as a Java setVisible(true, false).

    on_campus               -- request came from an RHPL public IP range
    authed                  -- patron holds a valid card-verified session
    in_house_access         -- the resource's InHouseAccess enum (1/2/3)
    remote_access           -- the resource's RemoteAccess enum (1/2/3)
    patron_code_id          -- the authed patron's PatronCodeID, if known
                               (set by the login flow after PAPI basicdata)
    blocked_patron_code_ids -- the resource's block-list; empty/None means
                               no patron-code restriction. Mirrors Polaris's
                               "patron codes to restrict" UI: a selected
                               code blocks that patron type.
    """
    blocked = list(blocked_patron_code_ids or [])

    if on_campus:
        # In-library IP. Use InHouseAccess.
        if in_house_access == ACCESS_OPEN:
            return GRANT
        if in_house_access == ACCESS_IP_ONLY:
            # Polaris's IP-grant carried no patron identity; match that.
            return GRANT
        # ACCESS_CARD -- need to know the patron's code before deciding.
        if not authed:
            return LOGIN
        return _check_patron_code(patron_code_id, blocked)

    # Off-site. Use RemoteAccess.
    if remote_access == ACCESS_IP_ONLY:
        # License forbids remote use; a card login cannot help.
        return DENY_OFFSITE
    if remote_access == ACCESS_OPEN:
        return GRANT
    # ACCESS_CARD
    if not authed:
        return LOGIN
    return _check_patron_code(patron_code_id, blocked)


def _check_patron_code(patron_code_id: int | None, blocked: list) -> str:
    """Once the patron is authed, enforce the per-resource block-list."""
    if not blocked:
        return GRANT
    if patron_code_id is None:
        # Authed flag set but we somehow never captured the code -- treat as
        # ineligible rather than silently grant. Fail closed when any
        # patron-code restriction is in play. (Shouldn't happen; the login
        # flow stores patron_code_id alongside esources_auth.)
        return DENY_PATRON_CODE
    return DENY_PATRON_CODE if int(patron_code_id) in {int(c) for c in blocked} else GRANT
