from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class KeycloakCallbackRequest(BaseModel):
    code: str
    redirect_uri: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    """Seconds until this token's idle deadline (sliding window)."""
    expires_in: int
    """Configured idle timeout in seconds (for SPA activity / refresh scheduling)."""
    idle_timeout_seconds: int
    """Configured absolute session max in seconds from login."""
    absolute_timeout_seconds: int


class ExchangeSSOCodeBody(BaseModel):
    code: str

