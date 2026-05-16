import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "http://localhost:5678")
N8N_PUBLIC_URL = os.getenv("N8N_PUBLIC_URL", N8N_BASE_URL)
N8N_API_KEY = os.getenv("N8N_API_KEY", "")
N8N_API_KEY_PLACEHOLDERS = {
    "",
    "your_n8n_api_key",
    "your-api-key-here",
    "your-api-key",
}


def n8n_api_key_configured():
    return N8N_API_KEY.strip() not in N8N_API_KEY_PLACEHOLDERS


def n8n_headers():
    headers = {"Content-Type": "application/json"}
    if n8n_api_key_configured():
        headers["X-N8N-API-KEY"] = N8N_API_KEY.strip()
    return headers


def n8n_url(path):
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{N8N_BASE_URL.rstrip('/')}{normalized_path}"


def n8n_get(path, timeout=10):
    return requests.get(n8n_url(path), headers=n8n_headers(), timeout=timeout)


def n8n_post(path, payload=None, timeout=30, authenticated=True):
    headers = n8n_headers() if authenticated else {"Content-Type": "application/json"}
    return requests.post(
        n8n_url(path),
        json=payload or {},
        headers=headers,
        timeout=timeout,
    )


def n8n_put(path, payload=None, timeout=30):
    return requests.put(
        n8n_url(path),
        json=payload or {},
        headers=n8n_headers(),
        timeout=timeout,
    )


def n8n_delete(path, timeout=10):
    return requests.delete(n8n_url(path), headers=n8n_headers(), timeout=timeout)
