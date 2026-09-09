"""Database-driven RBAC dependencies.

Permissions are read from the roles_permissions table on every request, so an
admin editing a role's permission set takes effect immediately (no redeploy).
"""
import uuid
from typing import Any

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import decode_token
from app.db.pool import afetch_one

_bearer = HTTPBearer(auto_error=False)


class AuthUser:
    def __init__(self, row: dict):
        self.id = str(row["id"])
        self.email = row["email"]
        self.full_name = row["full_name"]
        self.role = row["role_name"]
        self.permissions = set(row["permissions"] or [])
        self.institution_id = str(row["institution_id"]) if row["institution_id"] else None
        self.organization_id = str(row["organization_id"]) if row["organization_id"] else None
        self.consent_given = bool(row["consent_given"])
        self.raw = row

    def has(self, permission: str) -> bool:
        if "*" in self.permissions:
            return True
        if permission in self.permissions:
            return True
        # wildcard support: "students.*" grants "students.view.institution"
        parts = permission.split(".")
        for i in range(1, len(parts)):
            if ".".join(parts[:i]) + ".*" in self.permissions:
                return True
        return False


async def get_current_user(
    request: Request, creds: HTTPAuthorizationCredentials | None = Depends(_bearer)
) -> AuthUser:
    if creds is None:
        # allow token passed via cookie-less query param for file downloads (rare); keep strict
        auth = request.headers.get("Authorization", "")
        if not auth.lower().startswith("bearer "):
            raise HTTPException(401, "Not authenticated")
        token = auth[7:]
    else:
        token = creds.credentials
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(401, "Invalid or expired token")
    user_id = payload.get("sub")
    row = await afetch_one(
        """
        select u.id, u.email, u.full_name, u.institution_id, u.organization_id,
               u.consent_given, r.name as role_name, r.permissions
        from users u join roles_permissions r on r.id = u.role_id
        where u.id = %s and u.is_active
        """,
        (uuid.UUID(user_id),),
    )
    if row is None:
        raise HTTPException(401, "User not found or disabled")
    return AuthUser(row)


def require_perm(permission: str):
    async def checker(user: AuthUser = Depends(get_current_user)) -> AuthUser:
        if not user.has(permission):
            raise HTTPException(
                403,
                f"Permission denied: '{permission}' required "
                f"(role '{user.role}' has {sorted(user.permissions)})",
            )
        return user

    return checker
