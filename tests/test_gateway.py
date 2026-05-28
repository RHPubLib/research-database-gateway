"""Tests for gateway.decide_access -- the access decision matrix.

Covers all 3 in_house_access values x 3 remote_access values x patron-code
block-list permutations. Keep this file fast (pure Python, no I/O).
"""
from esources.gateway import (ACCESS_CARD, ACCESS_IP_ONLY, ACCESS_OPEN, DENY_OFFSITE,
                     DENY_PATRON_CODE, GRANT, LOGIN, decide_access)


# --- On-campus matrix -------------------------------------------------------

def test_on_campus_open_is_grant():
    assert decide_access(on_campus=True, authed=False,
                         in_house_access=ACCESS_OPEN,
                         remote_access=ACCESS_CARD) == GRANT


def test_on_campus_ip_only_is_grant_without_code_check():
    # Matches Polaris's InHouseAccess=3 behaviour: IP wins, no patron identity.
    # Block-list is ignored because IP-grant skips code resolution entirely.
    assert decide_access(on_campus=True, authed=False,
                         in_house_access=ACCESS_IP_ONLY,
                         remote_access=ACCESS_CARD,
                         blocked_patron_code_ids=[2, 4]) == GRANT


def test_on_campus_card_required_forces_login_when_not_authed():
    # Makerspace case: card required even in-library so we can fetch the code.
    assert decide_access(on_campus=True, authed=False,
                         in_house_access=ACCESS_CARD,
                         remote_access=ACCESS_CARD) == LOGIN


def test_on_campus_card_required_with_authed_not_blocked():
    # Resident (1) using Makerspace, which blocks [2=Non-Resident, 4=MILibrary].
    assert decide_access(on_campus=True, authed=True,
                         in_house_access=ACCESS_CARD,
                         remote_access=ACCESS_CARD,
                         patron_code_id=1,
                         blocked_patron_code_ids=[2, 4]) == GRANT


def test_on_campus_card_required_with_authed_blocked():
    # Non-Resident (2) using Makerspace, which blocks Non-Residents.
    assert decide_access(on_campus=True, authed=True,
                         in_house_access=ACCESS_CARD,
                         remote_access=ACCESS_CARD,
                         patron_code_id=2,
                         blocked_patron_code_ids=[2, 4]) == DENY_PATRON_CODE


# --- Off-site matrix --------------------------------------------------------

def test_offsite_open_is_grant():
    assert decide_access(on_campus=False, authed=False,
                         in_house_access=ACCESS_IP_ONLY,
                         remote_access=ACCESS_OPEN) == GRANT


def test_offsite_ip_only_is_deny_offsite():
    # License forbids remote use -- a card login cannot help.
    assert decide_access(on_campus=False, authed=False,
                         in_house_access=ACCESS_IP_ONLY,
                         remote_access=ACCESS_IP_ONLY) == DENY_OFFSITE
    assert decide_access(on_campus=False, authed=True,
                         in_house_access=ACCESS_IP_ONLY,
                         remote_access=ACCESS_IP_ONLY,
                         patron_code_id=1) == DENY_OFFSITE


def test_offsite_card_required_no_session_is_login():
    assert decide_access(on_campus=False, authed=False,
                         in_house_access=ACCESS_IP_ONLY,
                         remote_access=ACCESS_CARD) == LOGIN


def test_offsite_card_required_authed_no_blocklist_is_grant():
    assert decide_access(on_campus=False, authed=True,
                         in_house_access=ACCESS_IP_ONLY,
                         remote_access=ACCESS_CARD,
                         patron_code_id=1) == GRANT


def test_offsite_card_required_authed_not_blocked_is_grant():
    # Staff (7) off-site using Pronunciator, which blocks [2, 4, 17].
    assert decide_access(on_campus=False, authed=True,
                         in_house_access=ACCESS_IP_ONLY,
                         remote_access=ACCESS_CARD,
                         patron_code_id=7,
                         blocked_patron_code_ids=[2, 4, 17]) == GRANT


def test_offsite_card_required_authed_blocked_is_deny():
    # Non-Resident (2) off-site trying to use Pronunciator.
    assert decide_access(on_campus=False, authed=True,
                         in_house_access=ACCESS_IP_ONLY,
                         remote_access=ACCESS_CARD,
                         patron_code_id=2,
                         blocked_patron_code_ids=[2, 4, 17]) == DENY_PATRON_CODE


def test_authed_but_missing_code_with_blocklist_denies():
    # Fail closed: if the block-list is non-empty but we never captured the
    # patron's code, treat as ineligible rather than silently grant.
    assert decide_access(on_campus=False, authed=True,
                         in_house_access=ACCESS_IP_ONLY,
                         remote_access=ACCESS_CARD,
                         patron_code_id=None,
                         blocked_patron_code_ids=[2]) == DENY_PATRON_CODE


def test_authed_missing_code_without_blocklist_grants():
    # No block-list -> no code needed; missing code is fine.
    assert decide_access(on_campus=False, authed=True,
                         in_house_access=ACCESS_IP_ONLY,
                         remote_access=ACCESS_CARD,
                         patron_code_id=None) == GRANT


def test_blocklist_accepts_string_or_int_members():
    # Defensive: CSV import may produce ints, but a future caller could pass
    # strings. The check normalises both sides to int.
    assert decide_access(on_campus=False, authed=True,
                         in_house_access=ACCESS_IP_ONLY,
                         remote_access=ACCESS_CARD,
                         patron_code_id=1,
                         blocked_patron_code_ids=["2", "7"]) == GRANT
    # And the inverse: string member matches int patron_code → blocked.
    assert decide_access(on_campus=False, authed=True,
                         in_house_access=ACCESS_IP_ONLY,
                         remote_access=ACCESS_CARD,
                         patron_code_id=2,
                         blocked_patron_code_ids=["2", "7"]) == DENY_PATRON_CODE
