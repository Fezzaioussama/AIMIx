"""Operational commands: ``python -m api.cli <command>`` from backend/.

llm-probe [PROMPT] [--model ID] [--list-models]   smoke-test provider credentials
create-user USERNAME                              add an account (asks for the password)
export-user USERNAME                              print everything an account holds (JSON)
delete-user USERNAME                              delete an account and all its data
import-django-db PATH                             copy data from the old Django database

export-user and delete-user answer a data-protection request made outside the
app (someone who can no longer sign in): check who is asking first.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from collections.abc import Callable
from pathlib import Path

from sqlalchemy.orm import Session

from api.db import Database
from api.exceptions import DomainError, NotFound
from api.models import User
from api.repositories import users
from api.repositories.legacy_import import import_django_database
from api.schemas.account import AccountExportOut
from api.services import account_data, accounts
from api.services.llm import get_provider
from api.services.llm_settings import environment_profile
from api.services.run_recorder import utcnow
from config.settings import get_settings


def llm_probe(args: argparse.Namespace) -> None:
    """Probes the backend/.env credentials; keys saved on the Settings page are per user."""
    profile = environment_profile()
    if args.list_models:
        print("\n".join(profile.models))
        return
    if not args.prompt:
        raise DomainError("Provide a prompt, or pass --list-models.")
    model = args.model or profile.default_model
    print(f"model: {model}")
    print(get_provider(profile).generate(args.prompt, model))


def create_user(args: argparse.Namespace) -> None:
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Password (again): "):
        raise DomainError("The passwords do not match.")
    settings = get_settings()
    with Database(settings.database_url).session() as session:
        credentials = accounts.Credentials(args.username, password)
        user = account_data.open_account(session, settings, credentials)
    print(f"Created user {user.username} (id {user.id}).")


def export_user(args: argparse.Namespace) -> None:
    settings = get_settings()
    with Database(settings.database_url).session() as session:
        user = _account(session, args.username)
        files = account_data.workspace_of(settings, user.id)
        export = account_data.export_account(
            session, user, files, account_data.ExportOptions(utcnow())
        )
        print(AccountExportOut.model_validate(export).model_dump_json(indent=2))


def delete_user(args: argparse.Namespace) -> None:
    prompt = f"Type {args.username} to delete this account, its files and all its data: "
    if input(prompt) != args.username:
        raise DomainError("Nothing was deleted.")
    settings = get_settings()
    with Database(settings.database_url).session() as session:
        user = _account(session, args.username)
        account_data.delete_account(session, user, account_data.workspace_of(settings, user.id))
    print(f"Deleted user {args.username} and all of its data.")


def _account(session: Session, username: str) -> User:
    user = users.get_by_username(session, username)
    if user is None:
        raise NotFound(f"There is no account named {username}.")
    return user


def import_django_db(args: argparse.Namespace) -> None:
    with Database(get_settings().database_url).session() as session:
        summary = import_django_database(session, Path(args.path))
    print(f"Imported {summary.users} users, {summary.pipelines} pipelines, {summary.steps} steps.")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m api.cli")
    commands = parser.add_subparsers(dest="command", required=True)

    probe = commands.add_parser("llm-probe", help="Send one prompt to the configured provider.")
    probe.add_argument("prompt", nargs="?")
    probe.add_argument("--model", default=None, help="Model id to use.")
    probe.add_argument("--list-models", action="store_true", help="Print the catalogue.")
    probe.set_defaults(handler=llm_probe)

    user = commands.add_parser("create-user", help="Create an account.")
    user.add_argument("username")
    user.set_defaults(handler=create_user)

    export = commands.add_parser("export-user", help="Print everything an account holds.")
    export.add_argument("username")
    export.set_defaults(handler=export_user)

    delete = commands.add_parser("delete-user", help="Delete an account and all its data.")
    delete.add_argument("username")
    delete.set_defaults(handler=delete_user)

    legacy = commands.add_parser("import-django-db", help="Copy the old Django database in.")
    legacy.add_argument("path", help="Path to the old db.sqlite3.")
    legacy.set_defaults(handler=import_django_db)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    handler: Callable[[argparse.Namespace], None] = args.handler
    try:
        handler(args)
    except DomainError as cause:
        print(f"{cause.code}: {cause.detail}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
