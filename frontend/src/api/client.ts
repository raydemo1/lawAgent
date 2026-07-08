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
  EvalJobResponse,
  EvalRerankMode,
  EvalRunOptions,
  EvalSummary,
  HealthResponse,
  ReviewApiResponse,
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

/** Upload guardrails — mirror the backend so upload failures are intercepted
 *  in the browser before they can become a network "trace". */
export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024; // 20 MB
export const ALLOWED_UPLOAD_SUFFIXES = [
  '.txt', '.md', '.markdown', '.pdf', '.docx', '.html', '.htm', '.json',
] as const;

/**
 * Validate an uploaded file before sending it to the backend.
 *
 * Catches unsupported file types, oversized files, and empty files so that
 * these mistakes surface as a clear, local error message instead of a failed
 * review trace or an opaque network error.
 *
 * @throws {ApiError} status 422 when the file fails validation.
 */
export function validateUploadFile(file: File): void {
  const name = file.name || 'unknown';
  const lowerName = name.toLowerCase();
  const dotIndex = lowerName.lastIndexOf('.');
  const dotSuffix = dotIndex >= 0 ? lowerName.slice(dotIndex) : '';
  if (!ALLOWED_UPLOAD_SUFFIXES.some((s) => lowerName.endsWith(s))) {
    throw new ApiError(
      422,
      `不支持的文件类型 ${dotSuffix || '（无后缀）'}。支持：.txt .md .pdf .docx .html .json`,
      '/api/review',
      { code: 'unsupported_file_type', filename: name },
    );
  }
  if (file.size === 0) {
    throw new ApiError(
      422,
      `文件 ${name} 为空，无法解析。`,
      '/api/review',
      { code: 'empty_file', filename: name },
    );
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    throw new ApiError(
      422,
      `文件 ${name} 大小 ${(file.size / 1024 / 1024).toFixed(1)} MB 超过上限 ${MAX_UPLOAD_BYTES / 1024 / 1024} MB。`,
      '/api/review',
      { code: 'file_too_large', filename: name, size: file.size, limit: MAX_UPLOAD_BYTES },
    );
  }
}

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
 * Extract a human-readable message from a structured FastAPI error detail.
 *
 * The backend returns `{"detail": {"code": "...", "message": "..."}}` for
 * file parse / upload errors. This helper pulls out the `message` so the
 * user sees a clear Chinese description of what went wrong (e.g. "无法解析
 * 文件 report.pdf：...") instead of a raw JSON dump.
 */
function extractStructuredErrorMessage(detail: unknown): string | null {
  if (!detail || typeof detail !== 'object') return null;
  // FastAPI wraps the payload as { detail: {...} } — handle both shapes.
  const inner = (detail as { detail?: unknown }).detail ?? detail;
  if (inner && typeof inner === 'object') {
    const message = (inner as { message?: unknown }).message;
    if (typeof message === 'string' && message.trim()) return message.trim();
  }
  return null;
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
 * Sends the user's question and either material text or an uploaded file to
 * the backend. When a file is provided, the backend saves it to the review
 * run directory and extracts text using docling — the file becomes part of
 * the review case history.
 *
 * @param question      The review question to answer.
 * @param materialText  The material text to review (used when no file).
 * @param file          Optional uploaded file (.txt, .md, .pdf, .docx, etc.)
 * @returns             The full review response.
 * @throws {ApiError}   On 400 (blank input / bad request) or 500 (server error).
 */
export async function submitReview(
  question: string,
  materialText: string,
  file?: File | null,
): Promise<ReviewApiResponse> {
  if (!question || !question.trim()) {
    throw new ApiError(0, 'question must not be blank', '/api/review');
  }
  if (!file && (!materialText || !materialText.trim())) {
    throw new ApiError(
      0,
      'material_text or file must be provided',
      '/api/review',
    );
  }

  // Intercept upload mistakes locally so they never become a network
  // "trace": unsupported types, empty files, and oversized files are
  // reported before the request is sent.
  if (file) {
    validateUploadFile(file);
  }

  const url = buildUrl('/api/review');
  const controller = new AbortController();
  const timeoutId = setTimeout(
    () => controller.abort('timeout'),
    120_000, // 2 min for file extraction + retrieval
  );

  let response: Response;
  try {
    if (file) {
      // Multipart form data for file upload
      const formData = new FormData();
      formData.append('question', question);
      formData.append('material_text', materialText || '');
      formData.append('file', file);
      response = await fetch(url, {
        method: 'POST',
        body: formData,
        signal: controller.signal,
      });
    } else {
      // Plain form data for text-only submission
      const formData = new FormData();
      formData.append('question', question);
      formData.append('material_text', materialText);
      response = await fetch(url, {
        method: 'POST',
        body: formData,
        signal: controller.signal,
      });
    }
  } catch (err) {
    clearTimeout(timeoutId);
    // Network / connection failure: give a clear, actionable message
    // rather than letting it look like a review trace.
    const reason = err instanceof Error ? err.message : String(err);
    const aborted = controller.signal.aborted;
    throw new ApiError(
      0,
      aborted
        ? `请求超时或被中断：${reason}。请检查网络后重试，或缩小文档体积。`
        : `无法连接到审查服务（网络错误）：${reason}。请确认后端服务已启动并重试。`,
      '/api/review',
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
    // Prefer the backend's structured message for file parse / upload
    // errors so the user sees exactly what went wrong.
    const message = extractStructuredErrorMessage(detail);
    const detailStr = detailToString(detail);
    throw new ApiError(
      response.status,
      message
        ? message
        : detailStr
          ? `Review failed (${response.status}): ${detailStr}`
          : `Review failed (${response.status})`,
      '/api/review',
      detail,
    );
  }

  return response.json();
}

/**
 * Trigger a full evaluation run on the backend.
 *
 * The backend runs every golden-set scenario, computes per-case and
 * per-mode metrics, caches the result for `getLatestEval`, and returns
 * the complete summary.
 *
 * The `rerank_mode` field selects which A/B arm to populate. The two arms
 * (``off`` and ``embedding``) are cached separately and can be switched
 * between in the dashboard via `getLatestEval(rerankMode)`.
 *
 * @returns           The freshly generated evaluation summary.
 * @throws {ApiError} On 400 (bad config) or 500 (server error).
 */
export async function runEvaluation(
  options: EvalRunOptions = {
    retrieval_mode: 'service',
    review_mode: 'llm',
    top_k: 10,
    max_workers: 4,
    rerank_mode: 'off',
    suite: 'full',
  },
): Promise<EvalJobResponse> {
  return request<EvalJobResponse>('/api/eval/run', {
    method: 'POST',
    body: JSON.stringify(options),
  });
}

export async function getEvalStatus(
  rerankMode: EvalRerankMode = 'off',
): Promise<EvalJobResponse> {
  return request<EvalJobResponse>(
    `/api/eval/status?rerank_mode=${encodeURIComponent(rerankMode)}`,
    {
      method: 'GET',
      timeoutMs: 10_000,
    },
  );
}

/**
 * Get the most recently cached evaluation summary for the given rerank arm.
 *
 * @returns           The cached evaluation summary, or `null` if no
 *                    evaluation has been run for this arm yet (HTTP 404).
 * @throws {ApiError} On non-404 errors (e.g. 500).
 */
export async function getLatestEval(
  rerankMode: EvalRerankMode = 'off',
): Promise<EvalSummary | null> {
  try {
    return await request<EvalSummary>(
      `/api/eval/latest?rerank_mode=${encodeURIComponent(rerankMode)}`,
      {
        method: 'GET',
      },
    );
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      return null;
    }
    throw err;
  }
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
