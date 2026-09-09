"""Auth: login (JWT), current user, student self-registration."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from app.core.rbac import AuthUser, get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.pool import afetch_one, atransaction

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    email: str
    password: str


class RegisterBody(BaseModel):
    email: str
    full_name: str
    password: str
    institution_id: str | None = None
    stream: str = "cse"


def _user_response(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "email": row["email"],
        "full_name": row["full_name"],
        "role": row["role_name"],
        "role_display": row["display_name"],
        "permissions": row["permissions"] or [],
        "institution_id": str(row["institution_id"]) if row["institution_id"] else None,
        "institution_name": row.get("institution_name"),
        "organization_id": str(row["organization_id"]) if row["organization_id"] else None,
        "organization_name": row.get("organization_name"),
        "consent_given": bool(row["consent_given"]),
    }


_SELECT = """
select u.id, u.email, u.full_name, u.consent_given,
       r.name as role_name, r.display_name, r.permissions,
       u.institution_id, i.name as institution_name,
       u.organization_id, o.name as organization_name
from users u
join roles_permissions r on r.id = u.role_id
left join institutions i on i.id = u.institution_id
left join organizations o on o.id = u.organization_id
where u.email = %s and u.is_active
"""


@router.post("/login")
async def login(body: LoginBody):
    email = body.email.lower().strip()
    stored = await afetch_one(
        "select password_hash from users where email = %s and is_active", (email,)
    )
    if stored is None or not verify_password(body.password, stored["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
    row = await afetch_one(_SELECT, (email,))
    token = create_access_token(str(row["id"]), {"role": row["role_name"]})
    return {"access_token": token, "token_type": "bearer", "user": _user_response(row)}


@router.get("/me")
async def me(user: AuthUser = Depends(get_current_user)):
    return _user_response(user.raw)


@router.post("/register")
async def register(body: RegisterBody):
    email = body.email.lower().strip()
    if await afetch_one("select id from users where email = %s", (email,)):
        raise HTTPException(409, "An account with this email already exists")
    role = await afetch_one("select id from roles_permissions where name = 'student'")
    if role is None:
        raise HTTPException(500, "roles not seeded")
    row = await afetch_one(
        """
        insert into users (email, full_name, password_hash, role_id, institution_id)
        values (%s, %s, %s, %s, %s)
        returning id, email, full_name
        """,
        (email, body.full_name, hash_password(body.password), role["id"],
         uuid.UUID(body.institution_id) if body.institution_id else None),
    )
    async with atransaction() as cur:
        await cur.execute(
            """
            insert into student_profiles (user_id, stream)
            values (%s, %s)
            """,
            (row["id"], body.stream),
        )
    full = await afetch_one(_SELECT, (email,))
    token = create_access_token(str(row["id"]), {"role": full["role_name"]})
    return {"access_token": token, "token_type": "bearer", "user": _user_response(full)}
