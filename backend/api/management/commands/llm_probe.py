"""Send one prompt to the configured provider — a smoke test for credentials.

Replaces the old backend/test_llm_standalone.py, which ran an input() call at
import time and therefore broke `manage.py test` collection.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from api.exceptions import DomainError
from api.services.catalog import available_model_ids, default_model_id
from api.services.llm import get_provider


class Command(BaseCommand):
    help = "Send a single prompt to the configured LLM provider."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("prompt", nargs="?", help="Prompt to send.")
        parser.add_argument("--model", dest="model", default=None, help="Model id to use.")
        parser.add_argument(
            "--list-models", action="store_true", help="Print the catalogue and exit."
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if options["list_models"]:
            for model_id in available_model_ids():
                self.stdout.write(model_id)
            return

        prompt = options["prompt"]
        if not prompt:
            raise CommandError("Provide a prompt, or pass --list-models.")

        model = options["model"] or default_model_id()
        self.stdout.write(self.style.NOTICE(f"model: {model}"))
        try:
            reply = get_provider().generate(prompt, model)
        except DomainError as cause:
            raise CommandError(f"{cause.code}: {cause.detail}") from cause
        self.stdout.write(reply)
