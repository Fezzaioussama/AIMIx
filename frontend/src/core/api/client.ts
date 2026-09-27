import { clearTokens, getAccessToken } from '../auth/tokenStorage';

/**
 * Gateway for every backend call (AGENTS.md §7 Adapter/Interceptor): it is the
 * one place that attaches the bearer token, enforces a timeout (§6), and maps
 * backend errors to a single exception type. Features never call fetch directly.
 */
export const REQUEST_TIMEOUT_MS = 30_000;

/**
 * Anything that waits on a model: chat streams, pipeline generation and runs.
 * Matches the backend's LLM_TIMEOUT_SECONDS default (one hour).
 */
export const GENERATION_TIMEOUT_MS = 60 * 60 * 1000;

export class ApiError extends Error {
  readonly status: number;

  /**
   * Stable machine-readable code from the backend's error contract, e.g.
   * 'validation_error' or 'provider_timeout'. Branch on this rather than on
   * the message, which is meant for people. 'network_error' is set by this
   * module when the request never reached the server.
   */
  readonly code: string;

  constructor(message: string, status: number, code = 'error') {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

/**
 * The API answers every error with {"error": "<code>", "detail": "<message>"}.
 * Anything else reaching this function did not come from the API itself — a
 * proxy error page, say — so it degrades to the status line.
 */
function parseError(body: unknown, fallback: string): { code: string; detail: string } {
  if (typeof body !== 'object' || body === null) return { code: 'error', detail: fallback };
  const record = body as Record<string, unknown>;

  const code = typeof record['error'] === 'string' ? record['error'] : 'error';
  const detail = typeof record['detail'] === 'string' ? record['detail'].trim() : '';
  return { code, detail: detail || fallback };
}

async function toApiError(response: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // Non-JSON error body; fall back to the status line.
  }
  const { code, detail } = parseError(body, `Request failed (${response.status})`);
  return new ApiError(detail, response.status, code);
}

function authHeaders(extra?: HeadersInit): Headers {
  const headers = new Headers(extra);
  const token = getAccessToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  return headers;
}

/** A 401 means the token is gone or expired; drop it so the guard redirects. */
function handleUnauthorized(status: number): void {
  if (status === 401) clearTokens();
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  body?: unknown;
  timeoutMs?: number;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, timeoutMs = REQUEST_TIMEOUT_MS } = options;
  const headers = authHeaders(body === undefined ? undefined : { 'Content-Type': 'application/json' });

  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (cause) {
    const timedOut = cause instanceof DOMException && cause.name === 'TimeoutError';
    throw new ApiError(
      timedOut ? 'The request timed out.' : 'Could not reach the server.',
      0,
      timedOut ? 'timeout' : 'network_error',
    );
  }

  if (!response.ok) {
    handleUnauthorized(response.status);
    throw await toApiError(response);
  }

  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

/** Opens a streaming POST and yields decoded text chunks as they arrive. */
export async function* streamText(
  path: string,
  body: unknown,
  signal?: AbortSignal,
): AsyncGenerator<string> {
  const headers = authHeaders({ 'Content-Type': 'application/json' });
  const timeout = AbortSignal.timeout(GENERATION_TIMEOUT_MS);
  const response = await fetch(path, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
    signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
  });

  if (!response.ok) {
    handleUnauthorized(response.status);
    throw await toApiError(response);
  }
  if (!response.body)
    throw new ApiError('Streaming is not supported by this browser.', 0, 'unsupported');

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    yield decoder.decode(value, { stream: true });
  }
}
