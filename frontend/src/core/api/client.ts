import { clearTokens, getAccessToken, saveTokens } from '../auth/tokenStorage';
import { API } from './endpoints';
import type { AuthTokens } from './types';

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

/**
 * Uploading and reading a document: longer than a normal call, far shorter than a
 * generation. Text recognition of a long scan (DOCUMENT_OCR_MAX_PAGES pages, a few
 * seconds each) needs a few minutes.
 */
export const UPLOAD_TIMEOUT_MS = 300_000;

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

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  /** A FormData is sent as multipart (a file upload); anything else as JSON. */
  body?: unknown;
  timeoutMs?: number;
  /** Lets the caller cancel, e.g. when its component unmounts. */
  signal?: AbortSignal;
}

async function send(path: string, options: RequestOptions): Promise<Response> {
  const { method = 'GET', body, timeoutMs = REQUEST_TIMEOUT_MS, signal } = options;
  const isForm = body instanceof FormData;
  const headers = authHeaders(
    body === undefined || isForm ? undefined : { 'Content-Type': 'application/json' },
  );
  const timeout = AbortSignal.timeout(timeoutMs);

  try {
    return await fetch(path, {
      method,
      headers,
      body: body === undefined || isForm ? (body as FormData | undefined) : JSON.stringify(body),
      signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    });
  } catch (cause) {
    if (signal?.aborted) throw new ApiError('The request was cancelled.', 0, 'aborted');
    const timedOut = cause instanceof DOMException && cause.name === 'TimeoutError';
    throw new ApiError(
      timedOut ? 'The request timed out.' : 'Could not reach the server.',
      0,
      timedOut ? 'timeout' : 'network_error',
    );
  }
}

let refreshRequest: Promise<AuthTokens> | null = null;

async function performRefresh(): Promise<AuthTokens> {
  const response = await fetch(API.refresh, {
    method: 'POST',
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  });
  if (!response.ok) {
    clearTokens();
    throw await toApiError(response);
  }
  const tokens = (await response.json()) as AuthTokens;
  saveTokens(tokens);
  return tokens;
}

export function refreshAccessToken(): Promise<AuthTokens> {
  refreshRequest ??= performRefresh().finally(() => {
    refreshRequest = null;
  });
  return refreshRequest;
}

const AUTH_PATHS = new Set<string>([API.login, API.register, API.refresh, API.logout]);

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  let response = await send(path, options);
  if (response.status === 401 && !AUTH_PATHS.has(path)) {
    await refreshAccessToken();
    response = await send(path, options);
  }

  if (!response.ok) {
    if (response.status === 401) clearTokens();
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
  const options = { method: 'POST' as const, body, signal, timeoutMs: GENERATION_TIMEOUT_MS };
  let response = await send(path, options);
  if (response.status === 401) {
    await refreshAccessToken();
    response = await send(path, options);
  }

  if (!response.ok) {
    if (response.status === 401) clearTokens();
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
