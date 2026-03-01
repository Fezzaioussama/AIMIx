import os
import json
import requests
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

N8N_BASE_URL = os.getenv('N8N_BASE_URL', 'http://localhost:5678')
N8N_API_KEY = os.getenv('N8N_API_KEY', '')


def _n8n_headers():
    """Build headers for n8n API requests."""
    headers = {'Content-Type': 'application/json'}
    if N8N_API_KEY:
        headers['X-N8N-API-KEY'] = N8N_API_KEY
    return headers


@api_view(['GET'])
@permission_classes([AllowAny])
def list_workflows(request):
    """List all n8n workflows."""
    if not N8N_API_KEY:
        return Response({
            'data': [],
            'api_key_missing': True,
            'message': 'N8N_API_KEY not configured. Generate one in n8n Settings > n8n API, then add it to backend/.env'
        })
    try:
        resp = requests.get(
            f'{N8N_BASE_URL}/api/v1/workflows',
            headers=_n8n_headers(),
            timeout=10
        )
        return Response(resp.json(), status=resp.status_code)
    except requests.ConnectionError:
        return Response(
            {'error': 'Cannot connect to n8n. Make sure it is running (make run-n8n).'},
            status=503
        )
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_workflow(request, workflow_id):
    """Get details of a specific n8n workflow."""
    try:
        resp = requests.get(
            f'{N8N_BASE_URL}/api/v1/workflows/{workflow_id}',
            headers=_n8n_headers(),
            timeout=10
        )
        return Response(resp.json(), status=resp.status_code)
    except requests.ConnectionError:
        return Response({'error': 'Cannot connect to n8n.'}, status=503)
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['GET'])
@permission_classes([AllowAny])
def list_executions(request):
    """List n8n workflow executions."""
    if not N8N_API_KEY:
        return Response({'data': [], 'api_key_missing': True})
    try:
        resp = requests.get(
            f'{N8N_BASE_URL}/api/v1/executions',
            headers=_n8n_headers(),
            timeout=10
        )
        return Response(resp.json(), status=resp.status_code)
    except requests.ConnectionError:
        return Response({'error': 'Cannot connect to n8n.'}, status=503)
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([AllowAny])
def trigger_webhook(request, webhook_path):
    """Trigger an n8n webhook workflow."""
    try:
        resp = requests.post(
            f'{N8N_BASE_URL}/webhook/{webhook_path}',
            json=request.data,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        try:
            return Response(resp.json(), status=resp.status_code)
        except ValueError:
            return Response({'result': resp.text}, status=resp.status_code)
    except requests.ConnectionError:
        return Response({'error': 'Cannot connect to n8n.'}, status=503)
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['GET'])
@permission_classes([AllowAny])
def n8n_health(request):
    """Check if n8n is running."""
    try:
        resp = requests.get(f'{N8N_BASE_URL}/healthz', timeout=5)
        return Response({'status': 'connected', 'n8n_status': resp.status_code})
    except requests.ConnectionError:
        return Response({'status': 'disconnected'}, status=503)
