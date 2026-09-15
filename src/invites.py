"""Invite tokens for onboarding new editors.

An invite is a **single-use, email-bound, expiring** grant of a role. The raw
token exists only in the response to the admin who created it and in the link
they send; the database stores a SHA-256 hash, so a database dump cannot be
replayed into editor access.

Everything here is pure (no DB, no I/O) so the rules that actually gate access —
expiry, single use, revocation, and the email match — are unit-testable in
isolation. ``src/api/routers/admin.py`` holds the persistence around it.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

# Only 'editor' is invitable. 'listener' is what every Google sign-in already
# grants by default, and 'admin' stays a deliberate promotion on the admin page
# so a forwarded link can never hand out user management.
INVITABLE_ROLES = ("editor",)
DEFAULT_ROLE = "editor"

DEFAULT_EXPIRY_DAYS = 7

# 32 bytes -> a 43-character urlsafe token. Far beyond guessing, still short
# enough to paste into a text message without wrapping.
TOKEN_BYTES = 32


def generate_token() -> str:
    """Return a fresh, unguessable invite token (the secret half of the link)."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    """Return the stored form of a token. Never store the token itself."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    """Compare addresses case-insensitively and without stray whitespace."""
    return email.strip().lower()


def expiry_from(created_at: datetime, days: int = DEFAULT_EXPIRY_DAYS) -> datetime:
    """Return the expiry instant for an invite created at ``created_at``."""
    return created_at + timedelta(days=days)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: datetime) -> datetime:
    """Treat a naive timestamp as UTC so comparisons never raise."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def invite_status(invite: Dict[str, Any], now: Optional[datetime] = None) -> str:
    """Return 'revoked', 'redeemed', 'expired', or 'valid'.

    Checked in that order: an invite that was revoked *and* has since expired
    reads as revoked, because that is the fact the admin acted on.
    """
    now = now or _now()

    if invite.get("revoked_at"):
        return "revoked"
    if invite.get("redeemed_at"):
        return "redeemed"
    if _as_aware(invite["expires_at"]) <= _as_aware(now):
        return "expired"
    return "valid"


def redemption_error(
    invite: Dict[str, Any],
    email: str,
    now: Optional[datetime] = None,
) -> Optional[str]:
    """Return why ``email`` may not redeem ``invite``, or None if they may.

    The email match is what stops a forwarded or leaked link from granting
    editor to whoever opens it: the Google account that signs in has to be the
    address the invite was issued to.
    """
    status = invite_status(invite, now)
    if status == "revoked":
        return "This invite has been revoked."
    if status == "redeemed":
        return "This invite has already been used."
    if status == "expired":
        return "This invite has expired."

    if normalize_email(invite["email"]) != normalize_email(email):
        return "This invite was issued for a different email address."

    return None
