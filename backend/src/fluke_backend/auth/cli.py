"""Interactive account commands for the trusted-team operator."""

import argparse
import getpass
import sys
import warnings
from collections.abc import Sequence

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from fluke_backend.auth.accounts import AccountError, AccountService
from fluke_backend.database import Database
from fluke_backend.settings import Settings


class InvalidArgumentsError(Exception):
    pass


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InvalidArgumentsError("Invalid command or arguments")


def _parser() -> PrivateArgumentParser:
    parser = PrivateArgumentParser(prog="fluke-admin", description="Manage local FLUKE accounts")
    commands = parser.add_subparsers(
        dest="command", required=True, parser_class=PrivateArgumentParser
    )
    for name in ("create-user", "reset-password", "deactivate-user"):
        command = commands.add_parser(name)
        command.add_argument("--email", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    try:
        args, unknown = parser.parse_known_args(argv)
        if unknown:
            raise InvalidArgumentsError("Invalid command or arguments")
    except InvalidArgumentsError as error:
        print(str(error), file=sys.stderr)
        return 2

    try:
        settings = Settings()
        database = Database(settings)
        try:
            accounts = AccountService(database)
            if args.command == "deactivate-user":
                user = accounts.deactivate_user(args.email)
                print(f"Deactivated {user.email}")
            else:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", getpass.GetPassWarning)
                    password = getpass.getpass("Password: ")
                if args.command == "create-user":
                    user = accounts.create_user(args.email, password)
                    print(f"Created {user.email}")
                else:
                    user = accounts.reset_password(args.email, password)
                    print(f"Reset password for {user.email}")
        finally:
            database.close()
    except (EOFError, KeyboardInterrupt):
        print("Password entry cancelled", file=sys.stderr)
        return 2
    except getpass.GetPassWarning:
        print("Secure password prompt unavailable", file=sys.stderr)
        return 2
    except AccountError as error:
        print(str(error), file=sys.stderr)
        return 2
    except ValidationError:
        print("Application configuration is invalid", file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print("Account operation failed", file=sys.stderr)
        return 1
    return 0


def run() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    run()
