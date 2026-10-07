"""Operator CLI does not accept or print passwords as arguments."""

import getpass
import warnings

import pytest
from alembic import command

from fluke_backend.auth import cli

pytestmark = pytest.mark.postgres


def test_cli_prompts_and_never_prints_password(
    disposable_database, alembic_config, monkeypatch, capsys
):
    command.upgrade(alembic_config, "head")
    monkeypatch.setenv("FLUKE_DATABASE_URL", disposable_database.url.render_as_string(False))
    passwords = iter(["first secret phrase", "second secret phrase"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: next(passwords))

    assert cli.main(["create-user", "--email", "Member@Example.com"]) == 0
    assert cli.main(["reset-password", "--email", "member@example.com"]) == 0
    assert cli.main(["deactivate-user", "--email", "member@example.com"]) == 0
    output = capsys.readouterr()
    assert "member@example.com" in output.out
    assert "first secret phrase" not in output.out + output.err
    assert "second secret phrase" not in output.out + output.err


def test_cli_rejects_password_argument_without_echoing_it(monkeypatch, capsys):
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: pytest.fail("must not prompt"))
    assert (
        cli.main(["create-user", "--email", "member@example.com", "--password", "visible-secret"])
        == 2
    )
    output = capsys.readouterr()
    assert "visible-secret" not in output.out + output.err


def test_cli_rejects_insecure_password_prompt_before_reading(monkeypatch, capsys):
    monkeypatch.setenv("FLUKE_DATABASE_URL", "postgresql://localhost:1/unavailable")

    def insecure_prompt(_prompt):
        warnings.warn("Can not control echo", getpass.GetPassWarning, stacklevel=2)
        pytest.fail("Password would have been read with echo enabled")

    monkeypatch.setattr(cli.getpass, "getpass", insecure_prompt)
    assert cli.main(["create-user", "--email", "member@example.com"]) == 2
    output = capsys.readouterr()
    assert "Secure password prompt unavailable" in output.err
    assert "Can not control echo" not in output.err


def test_duplicate_account_error_omits_password(
    disposable_database, alembic_config, monkeypatch, capsys
):
    command.upgrade(alembic_config, "head")
    monkeypatch.setenv("FLUKE_DATABASE_URL", disposable_database.url.render_as_string(False))
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: "test secret phrase")
    assert cli.main(["create-user", "--email", "member@example.com"]) == 0
    assert cli.main(["create-user", "--email", "MEMBER@example.com"]) == 2
    output = capsys.readouterr()
    assert "test secret phrase" not in output.out + output.err
