import { clearTokens, getAccessToken } from '../auth/tokenStorage';

/**
 * Gateway for every backend call (AGENTS.md §7 Adapter/Interceptor): it is the
 * one place that attaches the bearer token, enforces a timeout (§6), and maps
 * backend errors to a single exception type. Features never call fetch directly.
 */
export const REQUEST_TIMEOUT_MS = 30_000;

/** Streaming responses legitimately stay open far longer than a JSON call. */
export const STREAM_TIMEOUT_MS = 300_000;

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

/**
 * The backend does not yet emit one consistent error shape, so this normalises
 * the variants actually in use: {detail}, {error}, {error, details} and DRF
 * field errors.
 */
function messageFromBody(body: unknown, fallback: string): string {
  if (typeof body !== 'object' || body === null) return fallback;
  const record = body as Record<string, unknown>;

  const direct = record['detail'] ?? record['error'];
  if (typeof direct === 'string' && direct.trim()) {
    const extra = record['details'];
    return typeof extra === 'string' && extra.trim() ? `${direct} ${extra}` : direct;
  }

  const firstFieldError = Object.values(record).find(
    (value): value is string[] => Array.isArray(value) && typeof value[0] === 'string',
  );
  return firstFieldError?.[0] ?? fallback;
}

async function toApiError(response: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // Non-JSON error body; fall back to the status line.
  }
  return new ApiError(messageFromBody(body, `Request failed (${response.status})`), response.status);
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
    throw new ApiError(timedOut ? 'The request timed out.' : 'Could not reach the server.', 0);
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
  const timeout = AbortSignal.timeout(STREAM_TIMEOUT_MS);
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
  if (!response.body) throw new ApiError('Streaming is not supported by this browser.', 0);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    yield decoder.decode(value, { stream: true });
  }
}
