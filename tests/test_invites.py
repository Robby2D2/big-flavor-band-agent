"""Assert-based tests for invite token rules (src/invites.py).

Pure logic — no DB, no network. These cover the four things that actually gate
access through an invite link: it expires, it is single-use, it can be revoked,
and it only works for the email it was issued to.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.invites import (  # noqa: E402
    DEFAULT_ROLE,
    INVITABLE_ROLES,
    expiry_from,
    generate_token,
    hash_token,
    invite_status,
    normalize_email,
    redemption_error,
)

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
EMAIL = "friend@example.com"


def make_invite(**overrides):
    invite = {
        "email": EMAIL,
        "role": "editor",
        "expires_at": NOW + timedelta(days=7),
        "redeemed_at": None,
        "revoked_at": None,
    }
    invite.update(overrides)
    return invite


# --- tokens ---------------------------------------------------------------

def test_generated_tokens_are_unique():
    assert len({generate_token() for _ in range(100)}) == 100


def test_generated_token_is_url_safe():
    token = generate_token()
    assert token
    assert all(c.isalnum() or c in "-_" for c in token)


def test_hash_is_stable_and_hides_the_token():
    token = generate_token()
    digest = hash_token(token)

    assert digest == hash_token(token)
    assert token not in digest
    assert len(digest) == 64


def test_different_tokens_hash_differently():
    assert hash_token("a") != hash_token("b")


# --- roles ----------------------------------------------------------------

def test_admin_is_not_invitable():
    assert "admin" not in INVITABLE_ROLES
    assert DEFAULT_ROLE == "editor"


# --- status ---------------------------------------------------------------

def test_fresh_invite_is_valid():
    assert invite_status(make_invite(), NOW) == "valid"


def test_past_expiry_is_expired():
    invite = make_invite(expires_at=NOW - timedelta(seconds=1))
    assert invite_status(invite, NOW) == "expired"


def test_expiry_boundary_is_expired():
    invite = make_invite(expires_at=NOW)
    assert invite_status(invite, NOW) == "expired"


def test_redeemed_invite_is_redeemed():
    invite = make_invite(redeemed_at=NOW - timedelta(days=1))
    assert invite_status(invite, NOW) == "redeemed"


def test_revoked_beats_redeemed_and_expired():
    invite = make_invite(
        revoked_at=NOW,
        redeemed_at=NOW,
        expires_at=NOW - timedelta(days=1),
    )
    assert invite_status(invite, NOW) == "revoked"


def test_naive_timestamps_are_treated_as_utc():
    invite = make_invite(expires_at=datetime(2026, 9, 21, 12, 0))
    assert invite_status(invite, NOW) == "valid"


def test_expiry_from_defaults_to_a_week():
    assert expiry_from(NOW) == NOW + timedelta(days=7)


# --- redemption -----------------------------------------------------------

def test_matching_email_may_redeem():
    assert redemption_error(make_invite(), EMAIL, NOW) is None


def test_email_match_ignores_case_and_whitespace():
    assert redemption_error(make_invite(), "  Friend@Example.COM ", NOW) is None


def test_different_email_may_not_redeem():
    error = redemption_error(make_invite(), "stranger@example.com", NOW)
    assert error == "This invite was issued for a different email address."


def test_expired_invite_may_not_be_redeemed():
    invite = make_invite(expires_at=NOW - timedelta(days=1))
    assert redemption_error(invite, EMAIL, NOW) == "This invite has expired."


def test_used_invite_may_not_be_redeemed_again():
    invite = make_invite(redeemed_at=NOW - timedelta(hours=1))
    assert redemption_error(invite, EMAIL, NOW) == "This invite has already been used."


def test_revoked_invite_may_not_be_redeemed():
    invite = make_invite(revoked_at=NOW - timedelta(hours=1))
    assert redemption_error(invite, EMAIL, NOW) == "This invite has been revoked."


def test_status_is_checked_before_the_email_match():
    """A stranger holding a revoked link learns nothing about who it was for."""
    invite = make_invite(revoked_at=NOW)
    assert redemption_error(invite, "stranger@example.com", NOW) == "This invite has been revoked."


def test_normalize_email_lowercases_and_strips():
    assert normalize_email("  MixedCase@Example.com  ") == "mixedcase@example.com"
