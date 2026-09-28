from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.security import validate_password_strength


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str
    tourist_id: int | None = None
    full_name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    role: str
    tourist_id: int | None = None

    class Config:
        from_attributes = True


class RefreshRequest(BaseModel):
    # Optional: a cookie-based client (see REFRESH_COOKIE_NAME) sends no body
    # at all. Kept for one release as a back-compat path for any client still
    # holding the refresh token itself rather than relying on the cookie.
    refresh_token: str | None = None


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., max_length=128)

    @field_validator("new_password")
    @classmethod
    def _strength(cls, v: str) -> str:
        validate_password_strength(v)
        return v
