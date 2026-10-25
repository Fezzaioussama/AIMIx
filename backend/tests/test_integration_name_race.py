"""Two requests that pass the name check together: the database decides, and the
loser gets the same refusal as a name taken before, not a server error."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from api.exceptions import ValidationFailed
from api.models import User
from api.repositories import integrations as repository
from api.repositories.integrations import IntegrationChanges


def named(name: str) -> IntegrationChanges:
    return IntegrationChanges(name=name, url="https://crm.example/mcp")


def test_a_name_taken_in_the_meantime_is_a_refusal_not_a_crash(
    session: Session, user: User
) -> None:
    repository.create(session, user, named("crm"))

    with pytest.raises(ValidationFailed, match="already have an integration named crm"):
        repository.create(session, user, named("crm"))  # as if the name check had passed

    # The failed write left the session usable, and nothing half-saved.
    assert repository.count(session, user) == 1
    repository.create(session, user, named("erp"))
    assert repository.count(session, user) == 2


def test_renaming_onto_a_name_taken_in_the_meantime_is_the_same_refusal(
    session: Session, user: User
) -> None:
    repository.create(session, user, named("crm"))
    other = repository.create(session, user, named("erp"))

    with pytest.raises(ValidationFailed, match="already have an integration named crm"):
        repository.update(session, other, IntegrationChanges(name="crm"))

    assert repository.count(session, user) == 2


def test_the_integration_limit_holds_when_others_were_saved_in_the_meantime(
    session: Session, user: User
) -> None:
    repository.create(session, user, named("one"), limit=2)
    repository.create(session, user, named("two"), limit=2)

    # As if this request had counted before the other two were saved.
    with pytest.raises(ValidationFailed, match="up to 2 integrations"):
        repository.create(session, user, named("three"), limit=2)

    assert repository.count(session, user) == 2
    assert not repository.name_taken(session, user, "three")
