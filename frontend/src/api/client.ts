/**
 * API client for the LawAgent review backend.
 *
 * Wraps the FastAPI endpoints exposed in `law_agent/review/api.py`:
 *
 * - `POST /api/review`      — run a full review case
 * - `POST /api/eval/run`    — trigger evaluation and cache result
 * - `GET  /api/eval/latest` — get the latest cached eval summary
 * - `GET  /api/health`      — health check
 *
 * In development the Vite dev server proxies `/api` to the backend
 * (see `vite.config.ts`), so requests can use relative URLs. For production
 * or non-proxied environments, set `VITE_API_BASE_URL` to the absolute
 * backend origin (e.g. `http://127.0.0.1:8000`).
 */

import type {
  EvalSummary,
  HealthResponse,
  ReviewResponse,
} from '../types/api';

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

/**
 * Base URL prepended to every request path. Defaults to an empty string so
 * that relative URLs (`/api/...`) are resolved against the current origin,
 * which works with the Vite dev-server proxy. Override via the
 * `VITE_API_BASE_URL` environment variable when the frontend is served from
 * a different origin than the API.
 */
const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/+$/, '') ?? '';

/** Default request timeout in milliseconds (30s). */
const DEFAULT_TIMEOUT_MS = 30_000;

// ---------------------------------------------------------------------------
// Error types
// ---------------------------------------------------------------------------

/**
 * Error thrown when an API request fails.
 *
 * Wraps the HTTP status code, a human-readable message, and the raw error
 * `detail` payload returned by FastAPI (which is typically a string for
 * `HTTPException` calls).
 */
export class ApiError extends Error {
  /** HTTP status code (e.g. 400, 404, 500). */
  readonly status: number;
  /** Endpoint path that failed, for diagnostics. */
  readonly endpoint: string;
  /** Raw `detail` field from the FastAPI error response, if present. */
  readonly detail: unknown;

  constructor(
    status: number,
    message: string,
    endpoint: string,
    detail?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.endpoint = endpoint;
    this.detail = detail;
  }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * Build a full URL from the configured base URL and a path.
 * Ensures exactly one slash separates the two parts.
 */
function buildUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}

/**
 * Extract a readable detail value from an error response body.
 *
 * FastAPI `HTTPException` responses use `{"detail": "..."}`, but validation
 * errors use `{"detail": [...]}`. This helper returns the raw value so the
 * caller can decide how to render it.
 */
function extractDetail(body: unknown): unknown {
  if (body && typeof body === 'object' && 'detail' in body) {
    return (body as { detail: unknown }).detail;
  }
  return body;
}

/**
 * Convert a detail value into a single human-readable string.
 */
function detailToString(detail: unknown): string {
  if (detail == null) return '';
  if (typeof detail === 'string') return detail;
  try {
    return JSON.stringify(detail);
  } catch {
    return String(detail);
  }
}

/**
 * Core request helper with timeout, JSON parsing, and structured errors.
 *
 * @typeParam T - Expected response body type.
 * @param path     API path beginning with `/api/...`.
 * @param options  Standard `fetch` init options plus an optional `timeoutMs`.
 * @returns        Parsed JSON response of type `T`.
 * @throws         {ApiError} on non-2xx responses, timeouts, or network errors.
 */
async function request<T>(
  path: string,
  options: RequestInit & { timeoutMs?: number } = {},
): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...fetchOptions } = options;
  const url = buildUrl(path);

  // Use AbortController to enforce a timeout. The abort reason is tagged so
  // we can distinguish timeouts from caller-initiated aborts.
  const controller = new AbortController();
  const timeoutId =
    timeoutMs > 0 ? setTimeout(() => controller.abort('timeout'), timeoutMs) : undefined;

  let response: Response;
  try {
    response = await fetch(url, {
      ...fetchOptions,
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
        ...(fetchOptions.body !== undefined
          ? { 'Content-Type': 'application/json' }
          : {}),
        ...fetchOptions.headers,
      },
    });
  } catch (err) {
    if (controller.signal.aborted) {
      throw new ApiError(
        0,
        `Request to ${path} timed out after ${timeoutMs}ms`,
        path,
      );
    }
    // Network error, DNS failure, CORS rejection, etc.
    throw new ApiError(
      0,
      `Network error while calling ${path}: ${
        err instanceof Error ? err.message : String(err)
      }`,
      path,
    );
  } finally {
    if (timeoutId !== undefined) clearTimeout(timeoutId);
  }

  // Read the response body once, as either JSON or text.
  const rawText = await response.text();
  let parsed: unknown = undefined;
  if (rawText) {
    try {
      parsed = JSON.parse(rawText);
    } catch {
      parsed = rawText;
    }
  }

  if (!response.ok) {
    const detail = extractDetail(parsed);
    const detailStr = detailToString(detail);
    const message = detailStr
      ? `API request to ${path} failed (${response.status}): ${detailStr}`
      : `API request to ${path} failed (${response.status})`;
    throw new ApiError(response.status, message, path, detail);
  }

  return parsed as T;
}

// ---------------------------------------------------------------------------
// Public API client functions
// ---------------------------------------------------------------------------

/**
 * Submit a review case for analysis.
 *
 * Sends the user's question and material text to the backend, which runs
 * the full review pipeline (fact extraction, hybrid retrieval, evidence
 * self-check, result construction) and returns the structured result.
 *
 * @param question      The review question to answer.
 * @param materialText  The material text to review.
 * @returns             The full review response.
 * @throws {ApiError}   On 400 (blank input / bad request) or 500 (server error).
 */
export async function submitReview(
  question: string,
  materialText: string,
): Promise<ReviewResponse> {
  if (!question || !question.trim()) {
    throw new ApiError(0, 'question must not be blank', '/api/review');
  }
  if (!materialText || !materialText.trim()) {
    throw new ApiError(0, 'material_text must not be blank', '/api/review');
  }

  return request<ReviewResponse>('/api/review', {
    method: 'POST',
    body: JSON.stringify({
      question,
      material_text: materialText,
    }),
  });
}

/**
 * Trigger a full evaluation run on the backend.
 *
 * The backend runs every golden-set scenario, computes per-case and
 * per-mode metrics, caches the result for `getLatestEval`, and returns
 * the complete summary.
 *
 * @returns           The freshly generated evaluation summary.
 * @throws {ApiError} On 400 (bad config) or 500 (server error).
 */
export async function runEvaluation(): Promise<EvalSummary> {
  return request<EvalSummary>('/api/eval/run', {
    method: 'POST',
    body: JSON.stringify({}),
  });
}

/**
 * Get the most recently cached evaluation summary.
 *
 * @returns           The cached evaluation summary, or `null` if no
 *                    evaluation has been run yet (HTTP 404).
 * @throws {ApiError} On non-404 errors (e.g. 500).
 */
export async function getLatestEval(): Promise<EvalSummary | null> {
  try {
    return await request<EvalSummary>('/api/eval/latest', {
      method: 'GET',
    });
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      return null;
    }
    throw err;
  }
}

/**
 * Upload a document file for text extraction.
 *
 * Sends a file to the backend, which uses the project's docling-based
 * extraction pipeline to convert it to plain text. The extracted text
 * can then be used as material_text in a subsequent submitReview call.
 *
 * @param file          The file to upload (.txt, .md, .pdf, .docx, .html, etc.)
 * @returns             The extracted text and metadata.
 * @throws {ApiError}   On 400 (unsupported type / empty) or 500 (extraction error).
 */
export async function uploadFile(
  file: File,
): Promise<{ filename: string; text: string; char_count: number; parser: string }> {
  const formData = new FormData();
  formData.append('file', file);

  const url = buildUrl('/api/upload');
  const controller = new AbortController();
  const timeoutId = setTimeout(
    () => controller.abort('timeout'),
    120_000, // 2 min timeout for large file extraction
  );

  let response: Response;
  try {
    response = await fetch(url, {
      method: 'POST',
      body: formData,
      signal: controller.signal,
    });
  } catch (err) {
    clearTimeout(timeoutId);
    throw new ApiError(
      0,
      err instanceof Error
        ? `Network error uploading file: ${err.message}`
        : 'Network error uploading file',
      '/api/upload',
      null,
    );
  }
  clearTimeout(timeoutId);

  if (!response.ok) {
    let detail: unknown = null;
    try {
      detail = await response.json();
    } catch {
      // Non-JSON error response
    }
    const detailStr = detailToString(detail);
    throw new ApiError(
      response.status,
      detailStr
        ? `File upload failed (${response.status}): ${detailStr}`
        : `File upload failed (${response.status})`,
      '/api/upload',
      detail,
    );
  }

  return response.json();
}

/**
 * Check whether the backend is reachable and healthy.
 *
 * @returns   `true` if the health endpoint responds with HTTP 200,
 *            `false` on any error (network failure, timeout, non-200).
 */
export async function checkHealth(): Promise<boolean> {
  try {
    const result = await request<HealthResponse>('/api/health', {
      method: 'GET',
      // Health checks should fail fast.
      timeoutMs: 5_000,
    });
    return result?.status === 'ok';
  } catch {
    return false;
  }
}
