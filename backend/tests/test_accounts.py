"""Operator account behavior against disposable PostgreSQL databases."""

import pytest
from alembic import command
from sqlalchemy import select

from fluke_backend.auth.accounts import (
    AccountExistsError,
    AccountNotFoundError,
    AccountService,
    InvalidEmailError,
)
from fluke_backend.auth.models import User
from fluke_backend.auth.passwords import verify_password
from fluke_backend.database import Database
from fluke_backend.settings import Settings

pytestmark = pytest.mark.postgres


@pytest.fixture
def account_database(disposable_database, alembic_config):
    command.upgrade(alembic_config, "head")
    database = Database(Settings(database_url=disposable_database.url.render_as_string(False)))
    try:
        yield database
    finally:
        database.close()


def test_account_stores_argon2_hash_and_normalized_email(account_database):
    created = AccountService(account_database).create_user(
        "  Alice@Example.COM  ", "correct horse battery"
    )
    with account_database.transaction() as session:
        stored = session.scalar(select(User).where(User.id == created.id))
        assert stored.email == "alice@example.com"
        assert stored.password_hash.startswith("$argon2id$")
        assert "correct horse battery" not in stored.password_hash
        assert verify_password("correct horse battery", stored.password_hash)
        assert not verify_password("wrong password", stored.password_hash)


def test_case_variants_cannot_create_duplicate_accounts(account_database):
    accounts = AccountService(account_database)
    accounts.create_user("Alice@Example.com", "first password")
    with pytest.raises(AccountExistsError):
        accounts.create_user(" alice@EXAMPLE.COM ", "second password")
    with account_database.transaction() as session:
        assert len(session.scalars(select(User)).all()) == 1


def test_invalid_email_is_rejected_before_storage(account_database):
    with pytest.raises(InvalidEmailError):
        AccountService(account_database).create_user("not-an-email", "correct horse battery")
    with account_database.transaction() as session:
        assert session.scalars(select(User)).all() == []


def test_password_reset_changes_hash(account_database):
    accounts = AccountService(account_database)
    user = accounts.create_user("member@example.com", "old secret phrase")
    with account_database.transaction() as session:
        old_hash = session.get(User, user.id).password_hash

    accounts.reset_password(" MEMBER@example.com ", "new secret phrase")

    with account_database.transaction() as session:
        stored = session.get(User, user.id)
        assert stored.password_hash != old_hash
        assert verify_password("new secret phrase", stored.password_hash)
        assert not verify_password("old secret phrase", stored.password_hash)


def test_deactivation_disables_account(account_database):
    accounts = AccountService(account_database)
    user = accounts.create_user("member@example.com", "correct horse battery")
    accounts.deactivate_user(" MEMBER@example.com ")

    with account_database.transaction() as session:
        stored = session.get(User, user.id)
        assert stored.is_active is False


def test_missing_account_cannot_be_reset_or_deactivated(account_database):
    accounts = AccountService(account_database)
    with pytest.raises(AccountNotFoundError):
        accounts.reset_password("missing@example.com", "new secret phrase")
    with pytest.raises(AccountNotFoundError):
        accounts.deactivate_user("missing@example.com")
