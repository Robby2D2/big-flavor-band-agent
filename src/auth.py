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
"""
import logging
import os
from typing import Optional

from fastapi import Depends, Header, HTTPException

logger = logging.getLogger(__name__)

SERVICE_SECRET_HEADER = "X-Service-Secret"
USER_ROLE_HEADER = "X-User-Role"

# Lowest privilege first; a role satisfies any requirement at or below its rank.
ROLE_HIERARCHY = ["listener", "editor", "admin"]


def _role_rank(role: Optional[str]) -> int:
    if role is None:
        return -1
    try:
        return ROLE_HIERARCHY.index(role.lower())
    except ValueError:
        return -1


def require_role(minimum_role: str):
    """Build a FastAPI dependency enforcing the service secret and a minimum role."""
    if minimum_role not in ROLE_HIERARCHY:
        raise ValueError(f"Unknown role: {minimum_role}")

    required_rank = _role_rank(minimum_role)

    async def dependency(
        x_service_secret: Optional[str] = Header(default=None, alias=SERVICE_SECRET_HEADER),
        x_user_role: Optional[str] = Header(default=None, alias=USER_ROLE_HEADER),
    ) -> str:
        expected_secret = os.environ.get("BACKEND_API_SECRET")
        if not expected_secret:
            # Fail closed: without a configured secret we cannot trust any caller.
            logger.error("BACKEND_API_SECRET is not set; rejecting protected request")
            raise HTTPException(status_code=401, detail="Server auth is not configured")

        if not x_service_secret or x_service_secret != expected_secret:
            raise HTTPException(status_code=401, detail="Missing or invalid service credentials")

        if _role_rank(x_user_role) < required_rank:
            raise HTTPException(status_code=403, detail="Insufficient role")

        return x_user_role.lower()

    return dependency
