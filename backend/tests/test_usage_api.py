"""Token usage, cost and run budgets over HTTP: what run payloads carry, how a
limit is set, reached and raised, and the user's usage report. Runs execute
inline (conftest.InlineRunExecutor), so a request returns a finished run."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from api.deps import app_settings
from api.models import Pipeline, Run, User
from api.repositories import users
from api.security import hash_password
from tests.conftest import TEST_SETTINGS, bearer, use_pipeline_generator
from tests.test_endpoints import make_pipeline
from tests.test_runs_api import start
from tests.usage_fakes import EXACT_COST, ModelCall, UsageAgent

#: Every step of ``make_pipeline`` has no role, so ``""`` addresses them all.
EVERY_STEP = ""
USAGE_KEYS = {"input_tokens", "output_tokens", "cost_usd", "cost_complete"}


def start_with(client: TestClient, pipeline: Pipeline, **body: Any) -> dict[str, Any]:
    response = client.post(f"/api/pipelines/{pipeline.id}/runs", json={"input": "seed", **body})
    assert response.status_code == 202, response.text
    payload: dict[str, Any] = response.json()
    return payload


def test_a_run_reports_its_usage_per_step_and_in_total(
    app: FastAPI, auth_client: TestClient, user: User, session: Session
) -> None:
    pipeline = make_pipeline(session, user, "Counted", steps=2)
    use_pipeline_generator(app, UsageAgent(calls={EVERY_STEP: 2}))

    run = auth_client.get(f"/api/runs/{start(auth_client, pipeline)['id']}").json()

    assert run["usage"] == {
        "input_tokens": 400,
        "output_tokens": 200,
        "cost_usd": 4 * EXACT_COST,
        "cost_complete": True,
    }
    for step in run["steps"]:
        assert (step["input_tokens"], step["output_tokens"]) == (200, 100)
        assert step["cost_usd"] == 2 * EXACT_COST
    assert (run["max_cost_usd"], run["max_tokens"]) == (None, None)


def test_the_history_shows_each_runs_cost_without_its_steps(
    app: FastAPI, auth_client: TestClient, user: User, session: Session
) -> None:
    pipeline = make_pipeline(session, user, "Listed", steps=2)
    use_pipeline_generator(app, UsageAgent())
    start(auth_client, pipeline)

    item = auth_client.get("/api/runs").json()["items"][0]

    assert "steps" not in item
    assert set(item["usage"]) == USAGE_KEYS
    assert item["usage"]["cost_usd"] == 2 * EXACT_COST
    assert item["usage"]["input_tokens"] == 200


def test_a_run_on_a_model_with_no_known_cost_says_so_but_keeps_its_tokens(
    app: FastAPI, auth_client: TestClient, user: User, session: Session
) -> None:
    pipeline = make_pipeline(session, user, "Unpriced")
    use_pipeline_generator(app, UsageAgent(call=ModelCall(cost_usd=None)))

    run = auth_client.get(f"/api/runs/{start(auth_client, pipeline)['id']}").json()

    assert run["usage"] == {
        "input_tokens": 100,
        "output_tokens": 50,
        "cost_usd": None,
        "cost_complete": False,
    }
    assert run["steps"][0]["cost_usd"] is None


def test_a_run_nobody_counted_has_zero_usage_and_nothing_missing(
    auth_client: TestClient, user: User, session: Session, fake_provider: Any
) -> None:
    pipeline = make_pipeline(session, user, "Silent")

    run = start(auth_client, pipeline)

    assert run["usage"] == {
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": None,
        "cost_complete": True,
    }


def test_a_run_stops_at_its_cost_limit_with_a_plain_message(
    app: FastAPI, auth_client: TestClient, user: User, session: Session
) -> None:
    pipeline = make_pipeline(session, user, "Capped", steps=2)
    use_pipeline_generator(app, UsageAgent(calls={EVERY_STEP: 20}))

    started = start_with(auth_client, pipeline, max_cost_usd=0.25)
    run = auth_client.get(f"/api/runs/{started['id']}").json()

    assert started["max_cost_usd"] == 0.25
    assert run["status"] == "failed"
    assert run["error"] == {
        "code": "budget_exceeded",
        "detail": "This run stopped at $0.25 because it reached its $0.25 limit.",
    }
    assert run["steps"][0]["error"]["code"] == "budget_exceeded"
    assert [step["status"] for step in run["steps"]] == ["failed", "pending"]
    assert run["usage"]["cost_usd"] == 4 * EXACT_COST


def test_a_run_stops_at_its_token_limit(
    app: FastAPI, auth_client: TestClient, user: User, session: Session
) -> None:
    pipeline = make_pipeline(session, user, "Token capped")
    use_pipeline_generator(app, UsageAgent(calls={EVERY_STEP: 20}, call=ModelCall(cost_usd=None)))

    run = start_with(auth_client, pipeline, max_tokens=400)

    assert run["max_tokens"] == 400
    assert run["error"]["code"] == "budget_exceeded"
    assert run["error"]["detail"] == (
        "This run stopped at 450 tokens because it reached its 400-token limit."
    )


def test_the_waiting_run_endpoint_takes_limits_and_reports_the_stop_as_a_conflict(
    app: FastAPI, auth_client: TestClient, user: User, session: Session
) -> None:
    pipeline = make_pipeline(session, user, "Waited for")
    use_pipeline_generator(app, UsageAgent(calls={EVERY_STEP: 20}))

    response = auth_client.post(
        f"/api/pipelines/{pipeline.id}/run", json={"input": "seed", "max_cost_usd": 0.25}
    )

    assert response.status_code == 409
    assert response.json()["error"] == "budget_exceeded"
    assert "reached its $0.25 limit" in response.json()["detail"]


def test_a_limit_that_makes_no_sense_is_a_400_and_saves_no_run(
    auth_client: TestClient, user: User, session: Session, fake_provider: Any
) -> None:
    pipeline = make_pipeline(session, user, "Refused")

    for body in ({"max_cost_usd": 0}, {"max_cost_usd": -1}, {"max_tokens": 0}, {"max_tokens": 1.5}):
        response = auth_client.post(
            f"/api/pipelines/{pipeline.id}/runs", json={"input": "seed", **body}
        )
        assert response.status_code == 400, body
        assert response.json()["error"] == "validation_error"

    assert auth_client.get("/api/runs").json() == {"items": [], "total": 0}


def stopped_run(
    app: FastAPI, client: TestClient, user: User, session: Session, limit: float = 0.25
) -> dict[str, Any]:
    pipeline = make_pipeline(session, user, "Resumable", steps=2)
    use_pipeline_generator(app, UsageAgent(calls={EVERY_STEP: 20}))
    started = start_with(client, pipeline, max_cost_usd=limit)
    run: dict[str, Any] = client.get(f"/api/runs/{started['id']}").json()
    assert run["error"]["code"] == "budget_exceeded"
    return run


def test_resuming_a_run_that_hit_its_limit_needs_a_higher_one(
    app: FastAPI, auth_client: TestClient, user: User, session: Session
) -> None:
    run = stopped_run(app, auth_client, user, session)
    use_pipeline_generator(app, UsageAgent())

    unchanged = auth_client.post(f"/api/runs/{run['id']}/resume")
    same_limit = auth_client.post(f"/api/runs/{run['id']}/resume", json={"max_cost_usd": 0.25})

    for refused in (unchanged, same_limit):
        assert refused.status_code == 409
        assert refused.json() == {
            "error": "budget_exceeded",
            "detail": (
                "This run already reached its $0.25 limit (it used $0.25). "
                "Raise the limit to resume it."
            ),
        }
    assert auth_client.get(f"/api/runs/{run['id']}").json()["status"] == "failed"


def test_resuming_with_a_higher_limit_finishes_the_run_and_adds_to_what_it_spent(
    app: FastAPI, auth_client: TestClient, user: User, session: Session
) -> None:
    run = stopped_run(app, auth_client, user, session)
    use_pipeline_generator(app, UsageAgent())

    resumed = auth_client.post(f"/api/runs/{run['id']}/resume", json={"max_cost_usd": 5})

    assert resumed.status_code == 200
    body = resumed.json()
    assert (body["status"], body["error"], body["max_cost_usd"]) == ("succeeded", None, 5.0)
    # The first attempt's four calls stay counted; the second adds the step it redid.
    assert body["usage"]["cost_usd"] > run["usage"]["cost_usd"]
    assert body["usage"]["input_tokens"] > run["usage"]["input_tokens"]


def test_a_resume_limit_that_makes_no_sense_is_a_400(
    app: FastAPI, auth_client: TestClient, user: User, session: Session
) -> None:
    run = stopped_run(app, auth_client, user, session)

    response = auth_client.post(f"/api/runs/{run['id']}/resume", json={"max_cost_usd": -3})

    assert response.status_code == 400
    assert response.json()["error"] == "validation_error"


def test_a_run_started_without_a_limit_takes_the_servers_default(
    app: FastAPI, auth_client: TestClient, user: User, session: Session
) -> None:
    app.dependency_overrides[app_settings] = lambda: TEST_SETTINGS.model_copy(
        update={"run_default_max_cost_usd": 0.1}
    )
    pipeline = make_pipeline(session, user, "Defaulted")
    use_pipeline_generator(app, UsageAgent(calls={EVERY_STEP: 20}))

    plain = start_with(auth_client, pipeline)
    own = start_with(auth_client, pipeline, max_cost_usd=3)

    assert plain["max_cost_usd"] == 0.1
    assert plain["error"]["code"] == "budget_exceeded"
    assert own["max_cost_usd"] == 3.0
    assert own["status"] == "succeeded"


def test_with_no_default_a_run_has_no_limit(
    auth_client: TestClient, user: User, session: Session, fake_provider: Any
) -> None:
    run = start(auth_client, make_pipeline(session, user, "Free to run"))

    assert (run["max_cost_usd"], run["max_tokens"]) == (None, None)


def run_once(
    app: FastAPI, client: TestClient, pipeline: Pipeline, agent: UsageAgent, **headers: Any
) -> dict[str, Any]:
    use_pipeline_generator(app, agent)
    response = client.post(
        f"/api/pipelines/{pipeline.id}/runs", json={"input": "seed"}, headers=headers or None
    )
    assert response.status_code == 202, response.text
    payload: dict[str, Any] = response.json()
    return payload


def test_the_report_totals_a_users_runs_and_breaks_them_down_per_pipeline(
    app: FastAPI, auth_client: TestClient, user: User, session: Session
) -> None:
    cheap = make_pipeline(session, user, "Cheap")
    dear = make_pipeline(session, user, "Dear")
    unpriced = make_pipeline(session, user, "Unpriced")
    run_once(app, auth_client, cheap, UsageAgent())
    run_once(app, auth_client, dear, UsageAgent(calls={EVERY_STEP: 4}))
    run_once(app, auth_client, dear, UsageAgent(calls={EVERY_STEP: 2}))
    run_once(app, auth_client, unpriced, UsageAgent(call=ModelCall(cost_usd=None)))

    report = auth_client.get("/api/usage").json()

    assert report["days"] == 30
    assert report["since"].endswith(("Z", "+00:00"))
    assert report["runs"] == 4
    assert report["usage"]["input_tokens"] == 100 * (1 + 4 + 2 + 1)
    assert report["usage"]["output_tokens"] == 50 * (1 + 4 + 2 + 1)
    assert report["usage"]["cost_usd"] == (1 + 4 + 2) * EXACT_COST
    # Some tokens come from a model with no known cost, so the cost is a floor.
    assert report["usage"]["cost_complete"] is False
    assert [entry["pipeline_name"] for entry in report["pipelines"]] == [
        "Dear",
        "Cheap",
        "Unpriced",
    ]
    dear_entry, cheap_entry, unpriced_entry = report["pipelines"]
    assert (dear_entry["pipeline_id"], dear_entry["runs"]) == (dear.id, 2)
    assert dear_entry["usage"]["cost_usd"] == 6 * EXACT_COST
    assert dear_entry["usage"]["cost_complete"] is True
    assert (cheap_entry["runs"], cheap_entry["usage"]["cost_usd"]) == (1, EXACT_COST)
    assert unpriced_entry["usage"] == {
        "input_tokens": 100,
        "output_tokens": 50,
        "cost_usd": None,
        "cost_complete": False,
    }


def test_the_report_of_a_user_with_no_runs_is_empty(auth_client: TestClient) -> None:
    report = auth_client.get("/api/usage").json()

    assert report["runs"] == 0
    assert report["pipelines"] == []
    assert report["usage"] == {
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": None,
        "cost_complete": True,
    }


def age(session: Session, run_id: int, days: float) -> None:
    moved = datetime.now(timezone.utc) - timedelta(days=days)
    session.execute(update(Run).where(Run.id == run_id).values(created_at=moved))
    session.commit()


def test_the_report_counts_only_the_period_asked_for(
    app: FastAPI, auth_client: TestClient, user: User, session: Session
) -> None:
    pipeline = make_pipeline(session, user, "Over time")
    recent = run_once(app, auth_client, pipeline, UsageAgent())
    last_month = run_once(app, auth_client, pipeline, UsageAgent(calls={EVERY_STEP: 2}))
    old = run_once(app, auth_client, pipeline, UsageAgent(calls={EVERY_STEP: 4}))
    age(session, recent["id"], 0.5)
    age(session, last_month["id"], 20)
    age(session, old["id"], 45)

    def cost(days: int) -> tuple[int, float]:
        report = auth_client.get("/api/usage", params={"days": days}).json()
        return report["runs"], report["usage"]["cost_usd"]

    assert cost(1) == (1, EXACT_COST)
    assert cost(30) == (2, 3 * EXACT_COST)
    assert cost(60) == (3, 7 * EXACT_COST)
    assert auth_client.get("/api/usage").json()["runs"] == 2


def test_the_report_never_counts_or_names_another_users_runs(
    app: FastAPI, auth_client: TestClient, user: User, session: Session
) -> None:
    other = users.create(session, "someone-else", hash_password("pw-for-someone-else-1", 1))
    mine = make_pipeline(session, user, "Mine")
    theirs = make_pipeline(session, other, "Secret project")
    run_once(app, auth_client, mine, UsageAgent())
    run_once(app, auth_client, theirs, UsageAgent(calls={EVERY_STEP: 8}), **bearer(other))

    own = auth_client.get("/api/usage").json()
    their = auth_client.get("/api/usage", headers=bearer(other)).json()

    assert (own["runs"], own["usage"]["cost_usd"]) == (1, EXACT_COST)
    assert [entry["pipeline_name"] for entry in own["pipelines"]] == ["Mine"]
    assert (their["runs"], their["usage"]["cost_usd"]) == (1, 8 * EXACT_COST)
    assert [entry["pipeline_name"] for entry in their["pipelines"]] == ["Secret project"]
    assert "Secret project" not in auth_client.get("/api/usage").text


def test_a_deleted_pipelines_runs_stay_in_the_report_under_its_name(
    app: FastAPI, auth_client: TestClient, user: User, session: Session
) -> None:
    pipeline = make_pipeline(session, user, "Short lived")
    run_once(app, auth_client, pipeline, UsageAgent(calls={EVERY_STEP: 2}))
    assert auth_client.delete(f"/api/pipelines/{pipeline.id}/").status_code == 204

    report = auth_client.get("/api/usage").json()

    assert report["runs"] == 1
    assert [(e["pipeline_id"], e["pipeline_name"]) for e in report["pipelines"]] == [
        (None, "Short lived")
    ]
    assert report["usage"]["cost_usd"] == 2 * EXACT_COST


def test_the_report_rejects_a_period_it_cannot_cover(auth_client: TestClient) -> None:
    for days in ("0", "-5", "367", "abc", "1.5"):
        response = auth_client.get("/api/usage", params={"days": days})
        assert response.status_code == 400, days
        assert response.json()["error"] == "validation_error"
    assert auth_client.get("/api/usage", params={"days": 366}).status_code == 200
    assert auth_client.get("/api/usage", params={"days": 1}).status_code == 200


def test_the_report_needs_a_signed_in_user(client: TestClient) -> None:
    response = client.get("/api/usage")

    assert response.status_code == 401
    assert response.json()["error"] == "not_authenticated"
