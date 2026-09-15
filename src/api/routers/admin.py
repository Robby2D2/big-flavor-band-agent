"""Health, user, and admin routes.

Data access goes through DatabaseManager methods on the shared injected pool
(issues #3/#8); admin routes are guarded by require_role("admin") (issue #1);
raw exceptions are left to propagate to the centralized error handlers (issue #9)
rather than being caught and re-raised with leaking detail.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends

from database import DatabaseManager
from src.auth import require_role
from src.invites import (
    INVITABLE_ROLES,
    expiry_from,
    generate_token,
    hash_token,
    invite_status,
    normalize_email,
    redemption_error,
)
from src.api.dependencies import (
    CreateInviteRequest,
    InviteTokenRequest,
    RedeemInviteRequest,
    UserCreate,
    UpdateRoleRequest,
    get_db,
)

logger = logging.getLogger("backend-api")

router = APIRouter()


# Health check
@router.get("/")
async def root():
    return {
        "status": "ok",
        "service": "BigFlavor Band Agent API",
        "version": "1.0.0"
    }


@router.get("/health")
async def health():
    return {"status": "healthy"}


# User management endpoints
#
# These sit behind the same trust boundary as everything else (issue #1): only
# the BFF can reach them. They are not admin-only — the BFF calls them for the
# person who just signed in — but without the service secret anything else on
# the Docker network could create users or enumerate roles.
@router.post("/api/users")
async def create_or_update_user(
    user: UserCreate,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("listener")),
):
    """Create or update a user in the database"""
    result = await db.upsert_user(
        user.id, user.email, user.name, user.picture
    )

    return {
        "id": result['id'],
        "email": result['email'],
        "name": result['name'],
        "picture": result['picture'],
        "role": result['role'],
        "created_at": result['created_at'].isoformat(),
        "updated_at": result['updated_at'].isoformat()
    }


@router.get("/api/users/{user_id}/role")
async def get_user_role(
    user_id: str,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("listener")),
):
    """Get a user's role from the database"""
    role = await db.get_user_role(user_id)

    if role is None:
        raise HTTPException(status_code=404, detail="User not found")

    return {"role": role}


# Admin endpoints
@router.get("/api/admin/users")
async def get_all_users(
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("admin")),
):
    """Get all users (admin only)"""
    results = await db.list_users()

    users = [
        {
            "id": row['id'],
            "email": row['email'],
            "name": row['name'],
            "picture": row['picture'],
            "role": row['role'],
            "created_at": row['created_at'].isoformat(),
            "updated_at": row['updated_at'].isoformat()
        }
        for row in results
    ]

    return {"users": users}


@router.put("/api/admin/users/role")
async def update_user_role(
    request: UpdateRoleRequest,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("admin")),
):
    """Update a user's role (admin only)"""
    # Validate role
    valid_roles = ['listener', 'editor', 'admin']
    if request.role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}")

    result = await db.set_user_role(request.user_id, request.role)

    if not result:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "id": result['id'],
        "email": result['email'],
        "name": result['name'],
        "role": result['role'],
        "updated_at": result['updated_at'].isoformat()
    }


# Invite endpoints
#
# The invite flow has two halves: an admin creates an invite here and copies the
# link, and the invitee redeems it through the BFF right after Google sign-in
# (see frontend/lib/invites.ts). The raw token is returned exactly once, at
# creation — only its hash is stored, so it cannot be shown again afterwards.
def _invite_response(invite: dict) -> dict:
    """Serialize an invite row for the API. Never includes the token or its hash."""
    return {
        "id": invite["id"],
        "email": invite["email"],
        "role": invite["role"],
        "status": invite_status(invite),
        "created_by": invite["created_by"],
        "created_at": invite["created_at"].isoformat(),
        "expires_at": invite["expires_at"].isoformat(),
        "redeemed_at": invite["redeemed_at"].isoformat() if invite["redeemed_at"] else None,
        "redeemed_by": invite["redeemed_by"],
        "revoked_at": invite["revoked_at"].isoformat() if invite["revoked_at"] else None,
    }


@router.post("/api/admin/invites")
async def create_invite(
    request: CreateInviteRequest,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("admin")),
):
    """Create an invite and return its token once (admin only)."""
    email = normalize_email(request.email)
    if "@" not in email:
        raise HTTPException(status_code=400, detail="A valid email address is required")

    if request.role not in INVITABLE_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid invite role. Must be one of: {', '.join(INVITABLE_ROLES)}",
        )

    token = generate_token()
    now = datetime.now(timezone.utc)
    invite = await db.create_invite(
        hash_token(token), email, request.role, request.created_by, expiry_from(now)
    )

    logger.info("Invite created for %s (role=%s)", email, request.role)

    # The only time the caller ever sees the token.
    return {**_invite_response(invite), "token": token}


@router.get("/api/admin/invites")
async def list_invites(
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("admin")),
):
    """List all invites and their current status (admin only)."""
    invites = await db.list_invites()
    return {"invites": [_invite_response(invite) for invite in invites]}


@router.delete("/api/admin/invites/{invite_id}")
async def revoke_invite(
    invite_id: int,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("admin")),
):
    """Revoke an unredeemed invite (admin only)."""
    invite = await db.revoke_invite(invite_id)

    if not invite:
        raise HTTPException(
            status_code=404, detail="No pending invite with that id (already used or revoked)"
        )

    return _invite_response(invite)


# The token travels in the body, not the path, so it stays out of access logs
# and browser history the way a `/api/invites/{token}` route would not.
@router.post("/api/invites/preview")
async def preview_invite(
    request: InviteTokenRequest,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("listener")),
):
    """Describe an invite so the landing page can show who it is for.

    Reachable before the invitee has signed in, so it is guarded by the service
    secret alone (the BFF forwards 'listener'). It reveals only what the holder
    of the link needs: the address to sign in with, the role, and the status.
    """
    invite = await db.get_invite_by_token_hash(hash_token(request.token))

    if not invite:
        raise HTTPException(status_code=404, detail="This invite link is not valid.")

    return {
        "email": invite["email"],
        "role": invite["role"],
        "status": invite_status(invite),
        "expires_at": invite["expires_at"].isoformat(),
    }


@router.post("/api/invites/redeem")
async def redeem_invite(
    request: RedeemInviteRequest,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("listener")),
):
    """Apply an invite's role to the user who just signed in."""
    invite = await db.get_invite_by_token_hash(hash_token(request.token))

    if not invite:
        raise HTTPException(status_code=404, detail="This invite link is not valid.")

    problem = redemption_error(invite, request.email)
    if problem:
        raise HTTPException(status_code=400, detail=problem)

    # Claim it before granting the role: this UPDATE is the single-use guarantee,
    # and losing the race means someone else already redeemed it.
    claimed = await db.redeem_invite(invite["id"], request.user_id)
    if not claimed:
        raise HTTPException(status_code=409, detail="This invite has already been used.")

    user = await db.set_user_role(request.user_id, claimed["role"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    logger.info("Invite %s redeemed by %s as %s", claimed["id"], request.email, claimed["role"])

    return {"role": user["role"], "email": user["email"]}
