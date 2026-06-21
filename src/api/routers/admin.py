"""Health, user, and admin routes.

Data access goes through DatabaseManager methods on the shared injected pool
(issues #3/#8); admin routes are guarded by require_role("admin") (issue #1);
raw exceptions are left to propagate to the centralized error handlers (issue #9)
rather than being caught and re-raised with leaking detail.
"""
from fastapi import APIRouter, HTTPException, Depends

from database import DatabaseManager
from src.auth import require_role
from src.api.dependencies import UserCreate, UpdateRoleRequest, get_db

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
@router.post("/api/users")
async def create_or_update_user(
    user: UserCreate,
    db: DatabaseManager = Depends(get_db)
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
    db: DatabaseManager = Depends(get_db)
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
