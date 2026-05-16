import requests
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from api.services.n8n import N8N_API_KEY, n8n_get, n8n_post


@api_view(["GET"])
@permission_classes([AllowAny])
def list_workflows(request):
    if not N8N_API_KEY:
        return Response(
            {
                "data": [],
                "api_key_missing": True,
                "message": "N8N_API_KEY not configured. Generate one in n8n Settings > n8n API, then add it to backend/.env",
            }
        )
    try:
        resp = n8n_get("/api/v1/workflows")
        return Response(resp.json(), status=resp.status_code)
    except requests.ConnectionError:
        return Response(
            {"error": "Cannot connect to n8n. Make sure it is running (make run-n8n)."},
            status=503,
        )
    except Exception as exc:
        return Response({"error": str(exc)}, status=500)


@api_view(["GET"])
@permission_classes([AllowAny])
def get_workflow(request, workflow_id):
    try:
        resp = n8n_get(f"/api/v1/workflows/{workflow_id}")
        return Response(resp.json(), status=resp.status_code)
    except requests.ConnectionError:
        return Response({"error": "Cannot connect to n8n."}, status=503)
    except Exception as exc:
        return Response({"error": str(exc)}, status=500)


@api_view(["GET"])
@permission_classes([AllowAny])
def list_executions(request):
    if not N8N_API_KEY:
        return Response({"data": [], "api_key_missing": True})
    try:
        resp = n8n_get("/api/v1/executions")
        return Response(resp.json(), status=resp.status_code)
    except requests.ConnectionError:
        return Response({"error": "Cannot connect to n8n."}, status=503)
    except Exception as exc:
        return Response({"error": str(exc)}, status=500)


@api_view(["POST"])
@permission_classes([AllowAny])
def trigger_webhook(request, webhook_path):
    try:
        resp = n8n_post(f"/webhook/{webhook_path}", request.data)
        try:
            return Response(resp.json(), status=resp.status_code)
        except ValueError:
            return Response({"result": resp.text}, status=resp.status_code)
    except requests.ConnectionError:
        return Response({"error": "Cannot connect to n8n."}, status=503)
    except Exception as exc:
        return Response({"error": str(exc)}, status=500)


@api_view(["GET"])
@permission_classes([AllowAny])
def n8n_health(request):
    try:
        resp = n8n_get("/healthz", timeout=5)
        return Response({"status": "connected", "n8n_status": resp.status_code})
    except requests.ConnectionError:
        return Response({"status": "disconnected"}, status=503)
