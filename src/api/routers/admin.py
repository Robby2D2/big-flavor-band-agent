"""Health, user, and admin routes."""
from fastapi import APIRouter, HTTPException

from database import DatabaseManager
from src.api.dependencies import UserCreate, UpdateRoleRequest

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
async def create_or_update_user(user: UserCreate):
    """Create or update a user in the database"""
    try:
        db_manager = DatabaseManager()
        await db_manager.connect()

        # Insert or update user
        query = """
            INSERT INTO users (id, email, name, picture, role, created_at, updated_at)
            VALUES ($1, $2, $3, $4, 'listener', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (id) DO UPDATE
            SET email = EXCLUDED.email,
                name = EXCLUDED.name,
                picture = EXCLUDED.picture,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id, email, name, picture, role, created_at, updated_at
        """

        async with db_manager.pool.acquire() as conn:
            result = await conn.fetchrow(query, user.id, user.email, user.name, user.picture)

        await db_manager.close()

        return {
            "id": result['id'],
            "email": result['email'],
            "name": result['name'],
            "picture": result['picture'],
            "role": result['role'],
            "created_at": result['created_at'].isoformat(),
            "updated_at": result['updated_at'].isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/users/{user_id}/role")
async def get_user_role(user_id: str):
    """Get a user's role from the database"""
    try:
        db_manager = DatabaseManager()
        await db_manager.connect()

        query = "SELECT role FROM users WHERE id = $1"

        async with db_manager.pool.acquire() as conn:
            result = await conn.fetchrow(query, user_id)

        await db_manager.close()

        if not result:
            raise HTTPException(status_code=404, detail="User not found")

        return {"role": result['role']}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Admin endpoints
@router.get("/api/admin/users")
async def get_all_users():
    """Get all users (admin only)"""
    try:
        db_manager = DatabaseManager()
        await db_manager.connect()

        query = """
            SELECT id, email, name, picture, role, created_at, updated_at
            FROM users
            ORDER BY created_at DESC
        """

        async with db_manager.pool.acquire() as conn:
            results = await conn.fetch(query)

        await db_manager.close()

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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/api/admin/users/role")
async def update_user_role(request: UpdateRoleRequest):
    """Update a user's role (admin only)"""
    try:
        # Validate role
        valid_roles = ['listener', 'editor', 'admin']
        if request.role not in valid_roles:
            raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}")

        db_manager = DatabaseManager()
        await db_manager.connect()

        query = """
            UPDATE users
            SET role = $1, updated_at = CURRENT_TIMESTAMP
            WHERE id = $2
            RETURNING id, email, name, role, updated_at
        """

        async with db_manager.pool.acquire() as conn:
            result = await conn.fetchrow(query, request.role, request.user_id)

        await db_manager.close()

        if not result:
            raise HTTPException(status_code=404, detail="User not found")

        return {
            "id": result['id'],
            "email": result['email'],
            "name": result['name'],
            "role": result['role'],
            "updated_at": result['updated_at'].isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
