"""
Backend API authorization.

The trust boundary is enforced here, not just in the Next.js BFF. Every protected
route depends on ``require_role(...)``, which checks two headers the trusted BFF injects:

- ``X-Service-Secret`` must equal ``BACKEND_API_SECRET`` (proves the caller is the BFF,
  not an arbitrary client on the Docker network). Missing/wrong -> 401.
- ``X-User-Role`` is the caller's role the BFF resolved after authenticating the user.
  Below the route's required role -> 403.

If ``BACKEND_API_SECRET`` is unset the dependency fails closed (rejects every protected
request) so the boundary is never silently open.

Some routes cannot decide on rank alone: a listener may remove a queued song they added
themselves but nobody else's (ACCT-15, RAD-13), so the route needs to know *who* is
calling, not only how privileged they are. ``require_caller(...)`` returns that identity
from a third header, ``X-User-Id``, and ``optional_caller`` reads it on routes that are
open to anyone but still record who acted. Either way it is believed only when the
service secret checks out -- otherwise anyone on the Docker network could claim to be
another user (ACCT-03).
"""
import logging
import os
from typing import NamedTuple, Optional

from fastapi import Header, HTTPException

logger = logging.getLogger(__name__)

SERVICE_SECRET_HEADER = "X-Service-Secret"
USER_ROLE_HEADER = "X-User-Role"
USER_ID_HEADER = "X-User-Id"

# Lowest privilege first; a role satisfies any requirement at or below its rank.
ROLE_HIERARCHY = ["listener", "editor", "admin"]


class Caller(NamedTuple):
    """Who is making a request, as far as the trusted BFF has vouched for them.

    Either field is None when it could not be verified. A route that needs one must
    treat None as a refusal, never as a default (ACCT-04).
    """

    role: Optional[str]
    user_id: Optional[str]


def _role_rank(role: Optional[str]) -> int:
    if role is None:
        return -1
    try:
        return ROLE_HIERARCHY.index(role.lower())
    except ValueError:
        return -1


def role_at_least(role: Optional[str], minimum_role: str) -> bool:
    """Whether ``role`` satisfies ``minimum_role``. An unknown role never does."""
    return _role_rank(role) >= _role_rank(minimum_role)


def _resolve_caller(
    x_service_secret: Optional[str],
    x_user_role: Optional[str],
    x_user_id: Optional[str],
    minimum_role: str,
) -> Caller:
    """Verify the service secret and the role, or raise. Shared by both dependencies."""
    expected_secret = os.environ.get("BACKEND_API_SECRET")
    if not expected_secret:
        # Fail closed: without a configured secret we cannot trust any caller.
        logger.error("BACKEND_API_SECRET is not set; rejecting protected request")
        raise HTTPException(status_code=401, detail="Server auth is not configured")

    if not x_service_secret or x_service_secret != expected_secret:
        raise HTTPException(status_code=401, detail="Missing or invalid service credentials")

    if not role_at_least(x_user_role, minimum_role):
        raise HTTPException(status_code=403, detail="Insufficient role")

    return Caller(role=x_user_role.lower(), user_id=x_user_id or None)


def require_role(minimum_role: str):
    """Build a FastAPI dependency enforcing the service secret and a minimum role."""
    if minimum_role not in ROLE_HIERARCHY:
        raise ValueError(f"Unknown role: {minimum_role}")

    async def dependency(
        x_service_secret: Optional[str] = Header(default=None, alias=SERVICE_SECRET_HEADER),
        x_user_role: Optional[str] = Header(default=None, alias=USER_ROLE_HEADER),
    ) -> str:
        return _resolve_caller(x_service_secret, x_user_role, None, minimum_role).role

    return dependency


def require_caller(minimum_role: str):
    """Build a FastAPI dependency enforcing the service secret and a minimum role,
    and returning **who** the caller is.

    Use this instead of ``require_role`` when authorization depends on the caller's
    identity as well as their rank.
    """
    if minimum_role not in ROLE_HIERARCHY:
        raise ValueError(f"Unknown role: {minimum_role}")

    async def dependency(
        x_service_secret: Optional[str] = Header(default=None, alias=SERVICE_SECRET_HEADER),
        x_user_role: Optional[str] = Header(default=None, alias=USER_ROLE_HEADER),
        x_user_id: Optional[str] = Header(default=None, alias=USER_ID_HEADER),
    ) -> Caller:
        return _resolve_caller(x_service_secret, x_user_role, x_user_id, minimum_role)

    return dependency


async def optional_caller(
    x_service_secret: Optional[str] = Header(default=None, alias=SERVICE_SECRET_HEADER),
    x_user_role: Optional[str] = Header(default=None, alias=USER_ROLE_HEADER),
    x_user_id: Optional[str] = Header(default=None, alias=USER_ID_HEADER),
) -> Caller:
    """Who the caller is, where being unidentified is allowed but not trusted.

    For routes that are open to any caller yet still want to record or reflect who
    acted. An unverified caller comes back as an empty ``Caller`` rather than a 401, so
    this changes who may reach a route: nothing. It only decides whose word about their
    own identity is taken.
    """
    expected_secret = os.environ.get("BACKEND_API_SECRET")
    if not expected_secret or x_service_secret != expected_secret:
        return Caller(role=None, user_id=None)

    return Caller(
        role=x_user_role.lower() if x_user_role else None,
        user_id=x_user_id or None,
    )
