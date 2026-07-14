import requests
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from api.services.n8n import N8N_PUBLIC_URL, n8n_api_key_configured, n8n_get, n8n_post
from api.services.n8n_workflow_generation import (
    WorkflowGenerationError,
    discover_local_n8n_node_catalog,
    generate_n8n_workflow,
)
from api.services.workflow_autofix import AutoFixError, autofix_workflow


def _proxy_response(resp):
    try:
        payload = resp.json()
    except ValueError:
        payload = {"result": resp.text}
    if resp.status_code in (401, 403):
        return Response(
            {
                "error": "n8n rejected the configured API key. Check N8N_API_KEY in backend/.env and make sure it has workflow and execution scopes.",
                "details": payload,
            },
            status=502,
        )
    return Response(payload, status=resp.status_code)


def _api_key_missing_response():
    return Response(
        {
            "data": [],
            "api_key_missing": True,
            "message": "N8N_API_KEY not configured. Use the embedded designer Settings > n8n API screen to create one, then add it to backend/.env.",
        },
        status=200,
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def list_workflows(request):
    if not n8n_api_key_configured():
        return _api_key_missing_response()
    try:
        resp = n8n_get("/api/v1/workflows")
        return _proxy_response(resp)
    except requests.ConnectionError:
        return Response(
            {"error": "Cannot connect to n8n. Make sure it is running (make run-n8n)."},
            status=503,
        )
    except Exception as exc:
        return Response({"error": str(exc)}, status=500)


@api_view(["GET"])
@permission_classes([AllowAny])
def list_node_types(request):
    catalog = discover_local_n8n_node_catalog()
    query = (request.query_params.get("q") or "").strip().lower()
    if query:
        catalog = [
            node
            for node in catalog
            if query in node["displayName"].lower() or query in node["type"].lower()
        ]
    return Response({"data": catalog[:300], "count": len(catalog)})


@api_view(["POST"])
@permission_classes([AllowAny])
def generate_workflow(request):
    if not n8n_api_key_configured():
        return _api_key_missing_response()

    prompt = (request.data or {}).get("prompt", "")
    should_create = (request.data or {}).get("create", True)

    try:
        generated = generate_n8n_workflow(prompt)
    except WorkflowGenerationError as exc:
        return Response({"error": str(exc)}, status=400)
    except Exception as exc:
        return Response({"error": f"Unable to generate workflow: {exc}"}, status=500)

    if not should_create:
        return Response(generated)

    try:
        resp = n8n_post("/api/v1/workflows", generated["workflow"], timeout=45)
    except requests.ConnectionError:
        return Response({"error": "Cannot connect to n8n."}, status=503)
    except Exception as exc:
        return Response({"error": str(exc)}, status=500)

    if resp.status_code >= 400:
        return _proxy_response(resp)

    try:
        created_workflow = resp.json()
    except ValueError:
        created_workflow = {"result": resp.text}

    return Response(
        {
            "message": "Draft workflow created in n8n.",
            "created_workflow": created_workflow,
            "plan": generated["plan"],
            "warning": generated["warning"],
            "node_catalog_size": generated["node_catalog_size"],
            "selected_node_types": generated["selected_node_types"],
        },
        status=201,
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def get_workflow(request, workflow_id):
    if not n8n_api_key_configured():
        return _api_key_missing_response()
    try:
        resp = n8n_get(f"/api/v1/workflows/{workflow_id}")
        return _proxy_response(resp)
    except requests.ConnectionError:
        return Response({"error": "Cannot connect to n8n."}, status=503)
    except Exception as exc:
        return Response({"error": str(exc)}, status=500)


@api_view(["GET"])
@permission_classes([AllowAny])
def list_executions(request):
    if not n8n_api_key_configured():
        return _api_key_missing_response()
    try:
        query = request.META.get("QUERY_STRING", "")
        suffix = f"?{query}" if query else ""
        resp = n8n_get(f"/api/v1/executions{suffix}")
        return _proxy_response(resp)
    except requests.ConnectionError:
        return Response({"error": "Cannot connect to n8n."}, status=503)
    except Exception as exc:
        return Response({"error": str(exc)}, status=500)


@api_view(["GET"])
@permission_classes([AllowAny])
def get_execution(request, execution_id):
    if not n8n_api_key_configured():
        return _api_key_missing_response()
    try:
        include_data = request.query_params.get("includeData", "true")
        resp = n8n_get(f"/api/v1/executions/{execution_id}?includeData={include_data}")
        return _proxy_response(resp)
    except requests.ConnectionError:
        return Response({"error": "Cannot connect to n8n."}, status=503)
    except Exception as exc:
        return Response({"error": str(exc)}, status=500)


@api_view(["POST"])
@permission_classes([AllowAny])
def activate_workflow(request, workflow_id):
    if not n8n_api_key_configured():
        return _api_key_missing_response()
    try:
        resp = n8n_post(f"/api/v1/workflows/{workflow_id}/activate", request.data)
        return _proxy_response(resp)
    except requests.ConnectionError:
        return Response({"error": "Cannot connect to n8n."}, status=503)
    except Exception as exc:
        return Response({"error": str(exc)}, status=500)


@api_view(["POST"])
@permission_classes([AllowAny])
def deactivate_workflow(request, workflow_id):
    if not n8n_api_key_configured():
        return _api_key_missing_response()
    try:
        resp = n8n_post(f"/api/v1/workflows/{workflow_id}/deactivate", request.data)
        return _proxy_response(resp)
    except requests.ConnectionError:
        return Response({"error": "Cannot connect to n8n."}, status=503)
    except Exception as exc:
        return Response({"error": str(exc)}, status=500)


@api_view(["POST"])
@permission_classes([AllowAny])
def retry_execution(request, execution_id):
    if not n8n_api_key_configured():
        return _api_key_missing_response()
    try:
        payload = request.data or {"loadWorkflow": True}
        resp = n8n_post(f"/api/v1/executions/{execution_id}/retry", payload)
        return _proxy_response(resp)
    except requests.ConnectionError:
        return Response({"error": "Cannot connect to n8n."}, status=503)
    except Exception as exc:
        return Response({"error": str(exc)}, status=500)


@api_view(["POST"])
@permission_classes([AllowAny])
def stop_execution(request, execution_id):
    if not n8n_api_key_configured():
        return _api_key_missing_response()
    try:
        resp = n8n_post(f"/api/v1/executions/{execution_id}/stop", request.data)
        return _proxy_response(resp)
    except requests.ConnectionError:
        return Response({"error": "Cannot connect to n8n."}, status=503)
    except Exception as exc:
        return Response({"error": str(exc)}, status=500)


@api_view(["POST"])
@permission_classes([AllowAny])
def autofix_workflow_endpoint(request, workflow_id):
    if not n8n_api_key_configured():
        return _api_key_missing_response()

    body = request.data or {}
    execution_id = body.get("execution_id") or body.get("executionId") or ""
    max_iterations = body.get("max_iterations") or body.get("maxIterations")

    if not execution_id:
        return Response(
            {"error": "Provide an execution_id of a failed execution to auto-fix."},
            status=400,
        )

    try:
        report = autofix_workflow(workflow_id, execution_id=str(execution_id), max_iterations=max_iterations)
    except AutoFixError as exc:
        return Response({"error": str(exc)}, status=400)
    except requests.ConnectionError:
        return Response({"error": "Cannot connect to n8n."}, status=503)
    except Exception as exc:
        return Response({"error": f"Auto-fix failed: {exc}"}, status=500)

    return Response(report, status=200)


@api_view(["POST"])
@permission_classes([AllowAny])
def trigger_webhook(request, webhook_path):
    try:
        resp = n8n_post(f"/webhook/{webhook_path}", request.data, authenticated=False)
        return _proxy_response(resp)
    except requests.ConnectionError:
        return Response({"error": "Cannot connect to n8n."}, status=503)
    except Exception as exc:
        return Response({"error": str(exc)}, status=500)


@api_view(["GET"])
@permission_classes([AllowAny])
def n8n_health(request):
    try:
        resp = n8n_get("/healthz", timeout=5)
        return Response(
            {
                "status": "connected",
                "n8n_status": resp.status_code,
                "api_key_configured": n8n_api_key_configured(),
            }
        )
    except requests.ConnectionError:
        return Response({"status": "disconnected"}, status=503)


@api_view(["GET"])
@permission_classes([AllowAny])
def n8n_info(request):
    return Response(
        {
            "editor_url": N8N_PUBLIC_URL.rstrip("/"),
            "api_key_configured": n8n_api_key_configured(),
        }
    )
