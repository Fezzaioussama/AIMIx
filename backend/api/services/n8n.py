import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "http://localhost:5678")
N8N_API_KEY = os.getenv("N8N_API_KEY", "")


def n8n_headers():
    headers = {"Content-Type": "application/json"}
    if N8N_API_KEY:
        headers["X-N8N-API-KEY"] = N8N_API_KEY
    return headers


def n8n_get(path, timeout=10):
    return requests.get(f"{N8N_BASE_URL}{path}", headers=n8n_headers(), timeout=timeout)


def n8n_post(path, payload, timeout=30):
    return requests.post(
        f"{N8N_BASE_URL}{path}",
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=timeout,
    )
