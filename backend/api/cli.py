"""Operational commands: ``python -m api.cli <command>`` from backend/.

llm-probe [PROMPT] [--model ID] [--list-models]   smoke-test provider credentials
create-user USERNAME                              add an account (asks for the password)
import-django-db PATH                             copy data from the old Django database
"""

from __future__ import annotations

import argparse
import getpass
import sys
from collections.abc import Callable
from pathlib import Path

from api.db import Database
from api.exceptions import DomainError
from api.repositories.legacy_import import import_django_database
from api.services import accounts
from api.services.catalog import available_model_ids, default_model_id
from api.services.llm import get_provider
from config.settings import get_settings


def llm_probe(args: argparse.Namespace) -> None:
    if args.list_models:
        print("\n".join(available_model_ids()))
        return
    if not args.prompt:
        raise DomainError("Provide a prompt, or pass --list-models.")
    model = args.model or default_model_id()
    print(f"model: {model}")
    print(get_provider().generate(args.prompt, model))


def create_user(args: argparse.Namespace) -> None:
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Password (again): "):
        raise DomainError("The passwords do not match.")
    settings = get_settings()
    with Database(settings.database_url).session() as session:
        user = accounts.register(
            session, args.username, password, settings.password_hash_iterations
        )
    print(f"Created user {user.username} (id {user.id}).")


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
