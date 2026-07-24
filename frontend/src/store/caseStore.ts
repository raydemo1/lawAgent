/**
 * Case store — localStorage-backed persistence for the review workbench.
 *
 * The store keeps an ordered list of `SavedCase` records (newest first) under
 * a single localStorage key. All mutations go through pure helper functions
 * that read → modify → write, so they are safe to call from React event
 * handlers. The `useCaseStore` hook re-renders subscribers on every change by
 * listening to a custom event + the native `storage` event (cross-tab sync).
 *
 * Storage layout:
 *   key:   `lawagent.cases.v1`
 *   value: JSON array of `SavedCase` (newest first)
 *
 * Quota safety: material text is capped at `MAX_MATERIAL_CHARS` before
 * storage; the full text is still sent to the backend for analysis.
 */

import { useCallback, useSyncExternalStore } from 'react';
import demoReview from '../data/demo-review.json';
import type { ReviewApiResponse } from '../types/api';
import { isReviewFailedResponse } from '../types/api';
import {
  type CaseFeedback,
  type CaseSummary,
  type CitationVerdict,
  type SavedCase,
  emptyFeedback,
} from '../types/case';

const STORAGE_KEY = 'lawagent.cases.v1';
const MAX_MATERIAL_CHARS = 8000;
const STORE_EVENT = 'lawagent:cases-change';
export const PUBLIC_DEMO_ENABLED =
  import.meta.env.VITE_PUBLIC_DEMO === 'true';
export const DEMO_CASE_ID = String(
  (demoReview as ReviewApiResponse & { review_case_id?: string }).review_case_id ??
    'crosscomply-demo-case',
);

const DEMO_CASE: SavedCase = {
  id: DEMO_CASE_ID,
  traceId: String(
    (demoReview as ReviewApiResponse & { trace_id?: string }).trace_id ??
      'crosscomply-demo-trace',
  ),
  savedAt: new Date().toISOString(),
  question: '这个场景是否需要数据出境安全评估？',
  materialText:
    '我们计划将境内用户的手机号、精确定位和设备标识传输至新加坡云服务商，用于个性化推荐和算法优化，预计覆盖约120万名用户。',
  materialSource: '内置真实示例',
  response: demoReview as ReviewApiResponse,
  feedback: null,
  isBadCase: false,
  badCaseReason: '',
};

// ---------------------------------------------------------------------------
// Low-level storage access (pure, no React)
// ---------------------------------------------------------------------------

function isBrowser(): boolean {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined';
}

function readRaw(): SavedCase[] {
  if (!isBrowser()) return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw === null) return PUBLIC_DEMO_ENABLED ? [DEMO_CASE] : [];
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed as SavedCase[];
  } catch {
    return [];
  }
}

function writeRaw(cases: SavedCase[]): void {
  if (!isBrowser()) return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(cases));
    // Notify same-tab subscribers (the storage event only fires cross-tab).
    window.dispatchEvent(new CustomEvent(STORE_EVENT));
  } catch {
    // Quota exceeded or serialization failure — swallow so the UI keeps
    // working in-memory for the rest of the session.
  }
}

function nowIso(): string {
  return new Date().toISOString();
}

function truncate(text: string, limit: number): string {
  if (text.length <= limit) return text;
  return text.slice(0, limit) + '…';
}

// ---------------------------------------------------------------------------
// Public mutations
// ---------------------------------------------------------------------------

/**
 * Persist a fresh review submission as a new `SavedCase`.
 *
 * If a case with the same `review_case_id` already exists (e.g. the user
 * re-submitted after a transient failure), it is replaced and bumped to the
 * top of the history.
 */
export function saveCase(
  response: ReviewApiResponse,
  question: string,
  materialText: string,
  materialSource: string | null = null,
): SavedCase {
  const id = isReviewFailedResponse(response)
    ? response.trace_id ?? `case-${Date.now()}`
    : response.review_case_id;
  const traceId = isReviewFailedResponse(response)
    ? (response.trace_id ?? '')
    : response.trace_id;

  const record: SavedCase = {
    id,
    traceId,
    savedAt: nowIso(),
    question: question.trim(),
    materialText: truncate(materialText, MAX_MATERIAL_CHARS),
    materialSource,
    response,
    feedback: null,
    isBadCase: false,
    badCaseReason: '',
  };

  const cases = readRaw().filter((c) => c.id !== id);
  writeRaw([record, ...cases]);
  return record;
}

/** Remove a case from the local history. */
export function deleteCase(id: string): void {
  writeRaw(readRaw().filter((c) => c.id !== id));
}

/** Clear every saved case. */
export function clearCases(): void {
  writeRaw([]);
}

/** Return a single case by id, or `null` if not found. */
export function getCase(id: string): SavedCase | null {
  return readRaw().find((c) => c.id === id) ?? null;
}

/** Return lightweight summaries for the sidebar list (newest first). */
export function listSummaries(): CaseSummary[] {
  return readRaw().map(toSummary);
}

function toSummary(c: SavedCase): CaseSummary {
  const risk = isReviewFailedResponse(c.response)
    ? 'failed'
    : c.response.review_result.risk_level;
  return {
    id: c.id,
    savedAt: c.savedAt,
    question: c.question,
    riskLevel: risk,
    isBadCase: c.isBadCase,
    hasFeedback: c.feedback !== null,
    conclusionUseful: c.feedback?.conclusionUseful ?? null,
  };
}

/**
 * Replace a case's feedback. Pass `null` to clear existing feedback.
 * The `updatedAt` timestamp is set automatically.
 */
export function setFeedback(id: string, feedback: CaseFeedback | null): void {
  const cases = readRaw();
  const idx = cases.findIndex((c) => c.id === id);
  if (idx === -1) return;
  cases[idx] = {
    ...cases[idx],
    feedback: feedback ? { ...feedback, updatedAt: nowIso() } : null,
  };
  writeRaw(cases);
}

/** Update a single citation verdict within a case's feedback. */
export function setCitationVerdict(
  id: string,
  chunkId: string,
  verdict: CitationVerdict | null,
): void {
  const cases = readRaw();
  const idx = cases.findIndex((c) => c.id === id);
  if (idx === -1) return;
  const base = cases[idx].feedback ?? emptyFeedback();
  const next: CaseFeedback = {
    ...base,
    citationVerdicts: { ...base.citationVerdicts },
    updatedAt: nowIso(),
  };
  if (verdict === null) {
    delete next.citationVerdicts[chunkId];
  } else {
    next.citationVerdicts[chunkId] = verdict;
  }
  cases[idx] = { ...cases[idx], feedback: next };
  writeRaw(cases);
}

/** Set whether the overall conclusion was useful. */
export function setConclusionUseful(id: string, useful: boolean | null): void {
  const cases = readRaw();
  const idx = cases.findIndex((c) => c.id === id);
  if (idx === -1) return;
  const base = cases[idx].feedback ?? emptyFeedback();
  cases[idx] = {
    ...cases[idx],
    feedback: { ...base, conclusionUseful: useful, updatedAt: nowIso() },
  };
  writeRaw(cases);
}

/** Update the free-text feedback fields. */
export function setFeedbackText(
  id: string,
  field: 'missingSources' | 'notes',
  value: string,
): void {
  const cases = readRaw();
  const idx = cases.findIndex((c) => c.id === id);
  if (idx === -1) return;
  const base = cases[idx].feedback ?? emptyFeedback();
  cases[idx] = {
    ...cases[idx],
    feedback: { ...base, [field]: value, updatedAt: nowIso() },
  };
  writeRaw(cases);
}

/** Toggle or set the bad-case flag with an optional reason. */
export function setBadCase(
  id: string,
  isBad: boolean,
  reason = '',
): void {
  const cases = readRaw();
  const idx = cases.findIndex((c) => c.id === id);
  if (idx === -1) return;
  cases[idx] = {
    ...cases[idx],
    isBadCase: isBad,
    badCaseReason: isBad ? reason : '',
  };
  writeRaw(cases);
}

// ---------------------------------------------------------------------------
// React binding via useSyncExternalStore
// ---------------------------------------------------------------------------

function subscribe(callback: () => void): () => void {
  if (!isBrowser()) return () => {};
  window.addEventListener(STORE_EVENT, callback);
  window.addEventListener('storage', callback);
  return () => {
    window.removeEventListener(STORE_EVENT, callback);
    window.removeEventListener('storage', callback);
  };
}

/**
 * React hook returning the current list of saved cases (newest first).
 * Re-renders on every store mutation, including cross-tab changes.
 */
export function useCaseStore(): SavedCase[] {
  const getSnapshot = useCallback(() => {
    // useSyncExternalStore compares snapshots by reference; cache the parsed
    // array on the module so identical state doesn't trigger re-renders.
    return cachedSnapshot();
  }, []);
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}

let snapshotCache: SavedCase[] | null = null;

function cachedSnapshot(): SavedCase[] {
  const fresh = readRaw();
  if (!snapshotCache || !shallowSameIds(snapshotCache, fresh)) {
    snapshotCache = fresh;
  }
  return snapshotCache;
}

function shallowSameIds(a: SavedCase[], b: SavedCase[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    if (a[i].id !== b[i].id) return false;
    if (a[i].feedback !== b[i].feedback) return false;
    if (a[i].isBadCase !== b[i].isBadCase) return false;
    if (a[i].badCaseReason !== b[i].badCaseReason) return false;
  }
  return true;
}
