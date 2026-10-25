"""A tool call's arguments as the owner reads them: structure kept, size bounded."""

from __future__ import annotations

import json
from datetime import date

from api.services.approvals.preview import CUT_KEY, ELLIPSIS, preview_arguments


def test_arguments_that_fit_are_shown_as_they_are() -> None:
    arguments = {"to": "ada@example.com", "cc": ["bob@example.com"], "urgent": True, "n": 2}

    shown, cut = preview_arguments(arguments, max_chars=500)

    assert shown == arguments
    assert cut is False


def test_values_json_cannot_hold_are_shown_as_text() -> None:
    shown, cut = preview_arguments({"on": date(2026, 10, 24)}, max_chars=500)

    assert shown == {"on": "2026-10-24"}
    assert cut is False


def test_a_long_text_is_shortened_and_the_rest_is_kept() -> None:
    arguments = {"to": "ada@example.com", "body": "word " * 400}

    shown, cut = preview_arguments(arguments, max_chars=300)

    assert cut is True
    assert shown["to"] == "ada@example.com"
    assert shown["body"].endswith(ELLIPSIS)
    assert len(shown["body"]) < len(arguments["body"])
    assert len(json.dumps(shown, ensure_ascii=False)) <= 300


def test_texts_nested_in_lists_and_objects_are_shortened_too() -> None:
    arguments = {"items": [{"note": "x" * 1000}, {"note": "short"}]}

    shown, cut = preview_arguments(arguments, max_chars=300)

    assert cut is True
    assert shown["items"][1] == {"note": "short"}
    assert shown["items"][0]["note"].endswith(ELLIPSIS)


def test_arguments_too_big_to_shorten_keep_only_their_start() -> None:
    arguments = {f"key{n}": n for n in range(2000)}

    shown, cut = preview_arguments(arguments, max_chars=200)

    assert cut is True
    assert set(shown) == {CUT_KEY}
    assert shown[CUT_KEY].startswith('{"key0": 0, "key1": 1')
    assert shown[CUT_KEY].endswith(ELLIPSIS)
    assert len(shown[CUT_KEY]) <= 200 + len(ELLIPSIS)
