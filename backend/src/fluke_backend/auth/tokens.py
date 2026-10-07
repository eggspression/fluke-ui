"""One-hour signed bearer tokens and active-user lookup."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from jwt import InvalidTokenError
from sqlalchemy import select

from fluke_backend.auth.accounts import InvalidEmailError, normalize_email
from fluke_backend.auth.models import User
from fluke_backend.auth.passwords import verify_password
from fluke_backend.database import Database
from fluke_backend.settings import Settings

TOKEN_DURATION = timedelta(hours=1)
ISSUER = "fluke-backend"


class AuthenticationError(Exception):
    """Authentication failed; callers should return a generic response."""


@dataclass(frozen=True)
class AuthenticatedUser:
    id: UUID
    email: str


@dataclass(frozen=True)
class IssuedToken:
    access_token: str
    expires_at: datetime
    user: AuthenticatedUser


class TokenService:
    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.secret = settings.jwt_secret.get_secret_value()

    def login(self, email: str, password: str) -> IssuedToken:
        try:
            normalized = normalize_email(email)
        except InvalidEmailError:
            raise AuthenticationError from None

        with self.database.transaction() as session:
            user = session.scalar(select(User).where(User.email == normalized))
            if (
                user is None
                or not user.is_active
                or not verify_password(password, user.password_hash)
            ):
                raise AuthenticationError
            identity = AuthenticatedUser(user.id, user.email)

        now = datetime.now(UTC)
        expires_at = now + TOKEN_DURATION
        token = jwt.encode(
            {"iss": ISSUER, "sub": str(identity.id), "iat": now, "exp": expires_at},
            self.secret,
            algorithm="HS256",
        )
        return IssuedToken(token, expires_at, identity)

    def authenticate(self, token: str) -> AuthenticatedUser:
        try:
            claims = jwt.decode(
                token,
                self.secret,
                algorithms=["HS256"],
                issuer=ISSUER,
                options={"require": ["iss", "sub", "iat", "exp"]},
            )
            if not isinstance(claims["sub"], str) or "sid" in claims:
                raise AuthenticationError
            user_id = UUID(claims["sub"])
        except (AuthenticationError, InvalidTokenError, ValueError, TypeError, KeyError):
            raise AuthenticationError from None

        with self.database.transaction() as session:
            user = session.get(User, user_id)
            if user is None or not user.is_active:
                raise AuthenticationError
            return AuthenticatedUser(user.id, user.email)
