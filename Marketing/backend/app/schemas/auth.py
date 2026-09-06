"""Auth DTOs — login, role switch, and token/user responses."""

import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class SwitchRoleRequest(BaseModel):
    """Switch the active role — must be one of the roles granted this user."""

    role: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    roles: list[str] = []
    active_role: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class AuthConfig(BaseModel):
    """Runtime auth capabilities the SPA reads on load."""

    environment: str
    password_login: bool = True
