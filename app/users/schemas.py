from pydantic import BaseModel

from app.auth.roles import Role


class MeResponse(BaseModel):
    sub: str
    email: str
    role: Role


class RoleUpdate(BaseModel):
    role: Role


class RoleResponse(BaseModel):
    sub: str
    role: Role
