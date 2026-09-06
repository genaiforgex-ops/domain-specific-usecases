from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import ORMBase


class UserResponse(ORMBase):
    id: UUID
    email: str
    display_name: str
    roles: list[str]
    is_active: bool = True
    last_login: datetime | None = None
    created_at: datetime | None = None


class DevLoginRequest(BaseModel):
    email: str


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class AuthConfigResponse(BaseModel):
    """Runtime auth config, read by the frontend on load."""
    environment: str
    sso_enabled: bool


class UserCreateRequest(BaseModel):
    email: str
    display_name: str
    password: str
    role: str


class UserUpdateRequest(BaseModel):
    display_name: str | None = None
    is_active: bool | None = None
    role: str | None = None


class ResetPasswordRequest(BaseModel):
    new_password: str
