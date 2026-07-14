import copy
import json
import os
import re
import time

from api.services.llm import get_ai_service
from api.services.n8n import n8n_get, n8n_post, n8n_put
from api.services.n8n_workflow_generation import parse_json_object


def _int_env(name, default, minimum=1):
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _float_env(name, default, minimum=0.1):
    try:
        return max(minimum, float(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


DEFAULT_ITERATION_CAP = _int_env("DEFAULT_ITERATION_CAP", 3)
POLL_TIMEOUT_SECONDS = _int_env("AUTOFIX_POLL_TIMEOUT", 20)
POLL_INTERVAL_SECONDS = _float_env("AUTOFIX_POLL_INTERVAL", 1.5)


SECRET_KEY_HINTS = re.compile(
    r"(authorization|cookie|api[-_]?key|token|secret|password|x-n8n-api-key)",
    re.IGNORECASE,
)

PATCH_PROMPT = """You are an n8n workflow debugger. Your job is to FIX the failing node automatically.

WORKFLOW CONTEXT:
- Workflow name: {workflow_name}
- Failing node "{node_name}" of type {node_type} (typeVersion {type_version})
- Upstream nodes (in execution order, name -> type):
{upstream_nodes}

FAILING NODE'S CURRENT PARAMETERS (JSON):
{node_parameters}

ERROR MESSAGE:
{error_message}

INPUT THE NODE RECEIVED (redacted, truncated; may be empty):
{node_input}

n8n HTTP Request node body cheat sheet (typeVersion >= 4):
- To send a JSON body, set: "sendBody": true, "contentType": "json", "specifyBody": "json", "jsonBody": "{{\\"key\\": \\"value\\"}}"
- The "jsonBody" field is a STRING containing JSON, NOT a nested object.
- For OpenAI-compatible chat APIs (OpenAI, OpenRouter, Together, Groq, etc.) the body must contain at least: "model" (string) and "messages" (array of objects with "role" and "content").
- To send headers: "sendHeaders": true, "headerParameters": {{ "parameters": [ {{ "name": "Content-Type", "value": "application/json" }} ] }}
- Authentication should stay as whatever the node already has; do not invent credential ids.

Return ONLY valid JSON matching this schema:
{{
  "explanation": "what was wrong and what you changed (under 200 chars)",
  "parameters": {{ ... full replacement parameters object for the failing node ... }},
  "needs_user_action": ""
}}

Hard rules:
1. ALWAYS attempt a concrete patch. Return a real `parameters` object with sensible defaults baked in.
2. ONLY set `parameters` to null and use `needs_user_action` when the error is clearly a CREDENTIAL / AUTH problem — for example: 401, 403, "credentials missing", "unauthorized", "invalid API key", "no credentials available". In that case tell the user which n8n Credential type to create.
3. Do NOT punt with `needs_user_action` for any of these — fix them in `parameters` instead:
   - empty input array / no items from upstream
   - missing body, missing required field, malformed JSON
   - wrong URL, wrong HTTP method, wrong content type
   - invalid expression, expression referencing missing field
   - generic "Bad request" / "JSON parsing failed" — bake reasonable defaults right into the node
4. If the failing node depends on input that the upstream did not produce, HARDCODE plausible defaults directly in the failing node's parameters. Do not rely on upstream items.
5. Output the FULL parameters object (not a diff). Preserve fields you are not changing.
6. NEVER include credentials, API keys, tokens, secrets, bearer values, or cookies in `parameters`.
7. Do NOT include `id`, `name`, `type`, `typeVersion`, or `position` — only `parameters` content.
"""


class AutoFixError(Exception):
    pass


def autofix_workflow(workflow_id, execution_id=None, max_iterations=None):
    """Run a bounded auto-correction loop against an n8n workflow.

    Returns a structured report describing every attempt.
    """
    cap = clamp_cap(max_iterations)
    report = {
        "workflow_id": workflow_id,
        "iteration_cap": cap,
        "iterations": [],
        "final_state": "unknown",
        "final_execution_id": execution_id,
        "needs_user_action": "",
    }

    workflow = fetch_workflow(workflow_id)
    if not workflow:
        raise AutoFixError("Workflow not found.")

    current_execution_id = execution_id

    for attempt in range(1, cap + 1):
        if not current_execution_id:
            report["final_state"] = "no_execution"
            return report

        execution = fetch_execution(current_execution_id)
        if not execution:
            report["final_state"] = "execution_missing"
            return report

        status = execution_status(execution)
        if status == "success":
            report["final_state"] = "success"
            report["final_execution_id"] = current_execution_id
            return report

        failure = diagnose_failure(execution, workflow)
        attempt_report = {
            "iteration": attempt,
            "execution_id": current_execution_id,
            "status": status,
            "failing_node": failure.get("node_name", ""),
            "error_message": failure.get("error_message", ""),
            "explanation": "",
            "patched": False,
            "new_execution_id": "",
            "needs_user_action": "",
        }

        if not failure.get("node_name"):
            attempt_report["explanation"] = "Could not identify a failing node in execution data."
            report["iterations"].append(attempt_report)
            report["final_state"] = "no_failure_signal"
            return report

        patch, llm_warning = request_patch_from_llm(failure)
        if llm_warning:
            attempt_report["explanation"] = llm_warning
            report["iterations"].append(attempt_report)
            report["final_state"] = "llm_unavailable"
            return report

        attempt_report["explanation"] = patch.get("explanation", "")[:300]
        if patch.get("_punt_overridden"):
            attempt_report["explanation"] = (
                (attempt_report["explanation"] + " ") if attempt_report["explanation"] else ""
            ) + patch["_punt_overridden"]
        needs_user_action = (patch.get("needs_user_action") or "").strip()
        if needs_user_action or not isinstance(patch.get("parameters"), dict):
            attempt_report["needs_user_action"] = (
                needs_user_action
                or "LLM could not produce a concrete patch. Open the node and inspect manually."
            )
            report["iterations"].append(attempt_report)
            report["final_state"] = "needs_user_action" if needs_user_action else "no_patch_generated"
            report["needs_user_action"] = attempt_report["needs_user_action"]
            return report

        try:
            apply_parameter_patch(workflow, failure["node_name"], patch["parameters"])
        except AutoFixError as exc:
            attempt_report["explanation"] = f"Could not apply patch: {exc}"
            report["iterations"].append(attempt_report)
            report["final_state"] = "patch_failed"
            return report

        try:
            put_workflow(workflow_id, workflow)
        except AutoFixError as exc:
            attempt_report["explanation"] = f"n8n rejected updated workflow: {exc}"
            report["iterations"].append(attempt_report)
            report["final_state"] = "update_failed"
            return report

        attempt_report["patched"] = True

        new_execution_id, retry_error = retry_execution(current_execution_id)
        if not new_execution_id:
            attempt_report["explanation"] += f" Retry failed: {retry_error}"
            report["iterations"].append(attempt_report)
            report["final_state"] = "retry_failed"
            return report

        attempt_report["new_execution_id"] = new_execution_id
        report["iterations"].append(attempt_report)

        wait_for_execution(new_execution_id)
        current_execution_id = new_execution_id
        report["final_execution_id"] = new_execution_id

        workflow = fetch_workflow(workflow_id) or workflow

    final_execution = fetch_execution(report["final_execution_id"])
    if final_execution and execution_status(final_execution) == "success":
        report["final_state"] = "success"
    else:
        report["final_state"] = "iteration_cap_reached"
    return report


def clamp_cap(value):
    if not value:
        return DEFAULT_ITERATION_CAP
    try:
        candidate = int(value)
    except (TypeError, ValueError):
        return DEFAULT_ITERATION_CAP
    return max(1, min(candidate, DEFAULT_ITERATION_CAP * 2))


def fetch_workflow(workflow_id):
    try:
        resp = n8n_get(f"/api/v1/workflows/{workflow_id}")
    except Exception:
        return None
    if resp.status_code >= 400:
        return None
    try:
        return resp.json()
    except ValueError:
        return None


def fetch_execution(execution_id):
    try:
        resp = n8n_get(f"/api/v1/executions/{execution_id}?includeData=true")
    except Exception:
        return None
    if resp.status_code >= 400:
        return None
    try:
        return resp.json()
    except ValueError:
        return None


def execution_status(execution):
    status = execution.get("status")
    if status:
        return status
    return "success" if execution.get("finished") else "running"


def diagnose_failure(execution, workflow):
    data = execution.get("data") or {}
    result_data = data.get("resultData") or {}
    run_data = result_data.get("runData") or {}
    last_node = result_data.get("lastNodeExecuted") or ""

    failing_node_name = ""
    error_message = ""
    node_input = []

    if last_node and isinstance(run_data.get(last_node), list) and run_data[last_node]:
        candidate = run_data[last_node][0]
        if isinstance(candidate, dict) and (candidate.get("error") or candidate.get("executionStatus") == "error"):
            failing_node_name = last_node
            error_message = extract_error_message(candidate.get("error") or {})
            node_input = candidate.get("data", {}).get("main", [[]])

    if not failing_node_name:
        for name, runs in run_data.items():
            if not isinstance(runs, list):
                continue
            for run in runs:
                if isinstance(run, dict) and (run.get("error") or run.get("executionStatus") == "error"):
                    failing_node_name = name
                    error_message = extract_error_message(run.get("error") or {})
                    node_input = run.get("data", {}).get("main", [[]])
                    break
            if failing_node_name:
                break

    top_level_error = result_data.get("error") or {}
    if not failing_node_name and isinstance(top_level_error, dict):
        error_node = top_level_error.get("node")
        if isinstance(error_node, dict):
            failing_node_name = error_node.get("name") or ""
    if not failing_node_name:
        failing_node_name = last_node

    if not error_message:
        error_message = extract_error_message(top_level_error)

    workflow_node = find_workflow_node(workflow, failing_node_name)

    return {
        "node_name": failing_node_name,
        "error_message": error_message or "Unknown error.",
        "node_input_preview": redact_and_truncate(node_input),
        "node_type": workflow_node.get("type", "") if workflow_node else "",
        "type_version": workflow_node.get("typeVersion", 1) if workflow_node else 1,
        "node_parameters": workflow_node.get("parameters", {}) if workflow_node else {},
        "workflow_name": workflow.get("name", "") if workflow else "",
        "upstream_nodes": collect_upstream_nodes(workflow, failing_node_name),
    }


def collect_upstream_nodes(workflow, target_node_name):
    """Return [(name, type), ...] for nodes that feed into target_node_name."""
    if not workflow or not target_node_name:
        return []
    connections = workflow.get("connections") or {}
    nodes_by_name = {n.get("name"): n for n in workflow.get("nodes") or []}

    upstream = []
    seen = set()
    queue = [target_node_name]
    while queue:
        current = queue.pop()
        for source, outputs in connections.items():
            for output_array in (outputs.get("main") or []):
                for link in output_array or []:
                    if not isinstance(link, dict):
                        continue
                    if link.get("node") == current and source not in seen:
                        seen.add(source)
                        node = nodes_by_name.get(source)
                        upstream.append((source, node.get("type", "") if node else ""))
                        queue.append(source)
    upstream.reverse()
    return upstream


CREDENTIAL_ERROR_PATTERNS = re.compile(
    r"(401|403|unauthor|forbidden|credentials? (missing|not (set|configured)|invalid)"
    r"|invalid (api[- ]?key|token|bearer)|no credentials? available|please configure (your )?credentials?)",
    re.IGNORECASE,
)


def looks_like_credential_error(error_message):
    return bool(CREDENTIAL_ERROR_PATTERNS.search(error_message or ""))


def extract_error_message(error):
    if not isinstance(error, dict):
        return str(error)[:400]
    parts = []
    for key in ("message", "description", "name"):
        value = error.get(key)
        if value:
            parts.append(str(value))
    context = error.get("context")
    if isinstance(context, dict):
        for key in ("messageText", "descriptionText"):
            value = context.get(key)
            if value:
                parts.append(str(value))
    cause = error.get("cause")
    if isinstance(cause, dict) and cause.get("message"):
        parts.append(str(cause["message"]))
    return " | ".join(parts)[:600] or "Unknown error."


def find_workflow_node(workflow, node_name):
    if not workflow or not node_name:
        return None
    for node in workflow.get("nodes") or []:
        if node.get("name") == node_name:
            return node
    return None


def redact_and_truncate(node_input):
    try:
        text = json.dumps(node_input, default=str)
    except (TypeError, ValueError):
        text = str(node_input)
    text = text[:1200]

    def _scrub(match):
        return f'"{match.group(1)}": "[redacted]"'

    text = re.sub(
        r'"([^"]+)"\s*:\s*"([^"]{12,})"',
        lambda m: _scrub(m) if SECRET_KEY_HINTS.search(m.group(1)) else m.group(0),
        text,
    )
    return text


def request_patch_from_llm(failure):
    ai_service, llm, ai_error = get_ai_service()
    if ai_error:
        return {}, f"AI provider unavailable: {ai_error}"

    upstream = failure.get("upstream_nodes") or []
    upstream_text = "\n".join(f"- {name} ({type_})" for name, type_ in upstream) or "- (none — failing node is the trigger or has no inputs)"

    prompt = PATCH_PROMPT.format(
        workflow_name=failure.get("workflow_name", "") or "(unnamed)",
        node_name=failure.get("node_name", ""),
        node_type=failure.get("node_type", ""),
        type_version=failure.get("type_version", 1),
        upstream_nodes=upstream_text,
        node_parameters=json.dumps(failure.get("node_parameters") or {}, indent=2)[:2000],
        error_message=failure.get("error_message", "")[:600],
        node_input=failure.get("node_input_preview", "")[:1200],
    )

    parsed, err = _ask_llm_for_patch(ai_service, llm, prompt)
    if err:
        return {}, err

    parsed = override_unjustified_punt(parsed, failure)

    if not isinstance(parsed.get("parameters"), dict) and not looks_like_credential_error(failure.get("error_message", "")):
        forced_prompt = (
            prompt
            + "\n\nYOUR PREVIOUS RESPONSE WAS REJECTED. The error above is NOT a credential / auth problem, so you MUST return a concrete `parameters` object with hardcoded sensible defaults. Do not set parameters to null. Do not use needs_user_action. Return JSON only."
        )
        retried, retry_err = _ask_llm_for_patch(ai_service, llm, forced_prompt)
        if not retry_err and isinstance(retried, dict) and isinstance(retried.get("parameters"), dict):
            parsed = retried

    return parsed, ""


def _ask_llm_for_patch(ai_service, llm, prompt):
    try:
        response = ai_service.generate_response(prompt=prompt, llm=llm)
        parsed = parse_json_object(response or "")
    except Exception as exc:
        return {}, f"Patch LLM call failed: {exc}"
    if not isinstance(parsed, dict):
        return {}, "LLM did not return a JSON object."
    return parsed, ""


def override_unjustified_punt(patch, failure):
    """If the LLM bailed to needs_user_action for a non-credential error, force a real patch attempt
    by clearing needs_user_action and asking the caller to retry. We do this in-place by stripping
    the punt fields and letting the loop treat the response as 'no patch' so we surface the issue
    instead of silently stopping the loop.
    """
    needs_action = (patch.get("needs_user_action") or "").strip()
    has_params = isinstance(patch.get("parameters"), dict)
    if has_params or not needs_action:
        return patch
    if looks_like_credential_error(failure.get("error_message", "")):
        return patch
    patch["needs_user_action"] = ""
    patch["_punt_overridden"] = (
        "Auto-fix: LLM tried to defer this to the user but the error is not a credential issue. "
        f"Original deferral: {needs_action}"
    )
    return patch


def apply_parameter_patch(workflow, node_name, new_parameters):
    if not isinstance(new_parameters, dict):
        raise AutoFixError("Patch parameters must be a JSON object.")
    nodes = workflow.get("nodes") or []
    for node in nodes:
        if node.get("name") == node_name:
            sanitized = strip_secret_fields(new_parameters)
            node["parameters"] = sanitized
            return
    raise AutoFixError(f"Node '{node_name}' not found in workflow.")


def strip_secret_fields(parameters):
    cleaned = copy.deepcopy(parameters)

    def _walk(value):
        if isinstance(value, dict):
            for key in list(value.keys()):
                if SECRET_KEY_HINTS.search(key):
                    value[key] = ""
                else:
                    _walk(value[key])
        elif isinstance(value, list):
            for item in value:
                _walk(item)

    _walk(cleaned)
    return cleaned


def put_workflow(workflow_id, workflow):
    payload = build_update_payload(workflow)
    try:
        resp = n8n_put(f"/api/v1/workflows/{workflow_id}", payload, timeout=30)
    except Exception as exc:
        raise AutoFixError(str(exc))
    if resp.status_code >= 400:
        try:
            body = resp.json()
        except ValueError:
            body = resp.text
        raise AutoFixError(f"HTTP {resp.status_code}: {str(body)[:300]}")
    return resp


def build_update_payload(workflow):
    return {
        "name": workflow.get("name") or "AIMIx Workflow",
        "nodes": workflow.get("nodes") or [],
        "connections": workflow.get("connections") or {},
        "settings": workflow.get("settings") or {"executionOrder": "v1"},
    }


def retry_execution(execution_id):
    try:
        resp = n8n_post(f"/api/v1/executions/{execution_id}/retry", {"loadWorkflow": True}, timeout=30)
    except Exception as exc:
        return "", str(exc)
    if resp.status_code >= 400:
        try:
            body = resp.json()
        except ValueError:
            body = resp.text
        return "", f"HTTP {resp.status_code}: {str(body)[:200]}"
    try:
        body = resp.json()
    except ValueError:
        return "", "n8n retry returned non-JSON response"
    new_id = body.get("id") or body.get("data", {}).get("id") or ""
    return str(new_id), ""


def wait_for_execution(execution_id):
    deadline = time.time() + POLL_TIMEOUT_SECONDS
    while time.time() < deadline:
        execution = fetch_execution(execution_id)
        if execution and execution_status(execution) not in {"running", "waiting", "new"}:
            return execution
        time.sleep(POLL_INTERVAL_SECONDS)
    return None
