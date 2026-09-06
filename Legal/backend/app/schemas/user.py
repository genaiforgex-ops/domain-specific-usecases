from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    role: str


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None


class InviteRequest(BaseModel):
    email: EmailStr
    full_name: str
    role: str


class AcceptInviteRequest(BaseModel):
    token: str
    password: str = Field(min_length=8)


class InviteTokenInfo(BaseModel):
    valid: bool
    email: str | None = None
    full_name: str | None = None
    detail: str | None = None


class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_active: bool
    iam_managed: bool = False
    iam_synced_at: datetime | None = None
    created_at: datetime
    last_login_at: datetime | None
    permissions: list[str] = []


class IamSyncResultOut(BaseModel):
    created: int
    updated: int
    deactivated: int
    unchanged: int


class InviteResult(BaseModel):
    user: UserOut
    email_sent: bool
    detail: str
