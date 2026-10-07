"""Versioned HTTP login and current-user dependency."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, SecretStr

from fluke_backend.auth.tokens import AuthenticatedUser, AuthenticationError, TokenService

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
bearer_scheme = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    email: str
    password: SecretStr


class UserResponse(BaseModel):
    id: UUID
    email: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    user: UserResponse


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _service(request: Request) -> TokenService:
    return TokenService(request.app.state.database, request.app.state.settings)


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    try:
        return _service(request).authenticate(credentials.credentials)
    except AuthenticationError:
        raise _unauthorized() from None


@router.post("/login", response_model=LoginResponse)
def login(request: Request, payload: LoginRequest) -> LoginResponse:
    try:
        issued = _service(request).login(payload.email, payload.password.get_secret_value())
    except AuthenticationError:
        raise _unauthorized() from None
    return LoginResponse(
        access_token=issued.access_token,
        expires_at=issued.expires_at,
        user=UserResponse(id=issued.user.id, email=issued.user.email),
    )


@router.get("/me", response_model=UserResponse)
def me(user: Annotated[AuthenticatedUser, Depends(get_current_user)]) -> UserResponse:
    return UserResponse(id=user.id, email=user.email)
