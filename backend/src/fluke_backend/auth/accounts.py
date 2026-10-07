"""Operator-owned account writes."""

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from fluke_backend.auth.models import User
from fluke_backend.auth.passwords import hash_password
from fluke_backend.database import Database


class AccountError(Exception):
    """Safe, operator-facing account failure."""


class AccountExistsError(AccountError):
    pass


class AccountNotFoundError(AccountError):
    pass


class InvalidEmailError(AccountError):
    pass


class InvalidPasswordError(AccountError):
    pass


def normalize_email(email: str) -> str:
    try:
        normalized = validate_email(email.strip(), check_deliverability=False).normalized.casefold()
    except EmailNotValidError:
        raise InvalidEmailError("Invalid email address") from None
    if len(normalized) > 320:
        raise InvalidEmailError("Invalid email address")
    return normalized


def _new_password_hash(password: str) -> str:
    try:
        return hash_password(password)
    except ValueError:
        raise InvalidPasswordError("Password cannot be empty") from None


class AccountService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_user(self, email: str, password: str) -> User:
        normalized = normalize_email(email)
        password_hash = _new_password_hash(password)
        try:
            with self.database.transaction() as session:
                user = User(email=normalized, password_hash=password_hash)
                session.add(user)
                session.flush()
            return user
        except IntegrityError as error:
            constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
            if constraint == "uq_users_email":
                raise AccountExistsError("Account already exists") from None
            raise

    def reset_password(self, email: str, password: str) -> User:
        normalized = normalize_email(email)
        password_hash = _new_password_hash(password)
        with self.database.transaction() as session:
            user = session.scalar(select(User).where(User.email == normalized).with_for_update())
            if user is None:
                raise AccountNotFoundError("Account not found")
            user.password_hash = password_hash
        return user

    def deactivate_user(self, email: str) -> User:
        normalized = normalize_email(email)
        with self.database.transaction() as session:
            user = session.scalar(select(User).where(User.email == normalized).with_for_update())
            if user is None:
                raise AccountNotFoundError("Account not found")
            user.is_active = False
        return user
