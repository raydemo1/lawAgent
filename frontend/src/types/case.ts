/**
 * Case-store domain types for the review workbench.
 *
 * A `SavedCase` is a full review submission persisted client-side so the
 * user can reopen past reviews, export reports, and attach human feedback
 * (including marking an unsatisfactory result as a bad case for later
 * evaluation improvement).
 *
 * Persistence is backed by `localStorage` (single-user workbench). The
 * stored shape is intentionally self-contained: the full `ReviewApiResponse`
 * — including the retrieval query plan and evidence chunks — is stored so a
 * reopened case can render the complete review chain without a round-trip
 * to the backend.
 */

import type { ReviewApiResponse } from './api';

/** Per-citation human feedback (keyed by `chunk_id`). */
export type CitationVerdict = 'correct' | 'wrong';

/** Human feedback attached to a saved review case. */
export interface CaseFeedback {
  /** Whether the overall conclusion was useful. `null` = not yet rated. */
  conclusionUseful: boolean | null;
  /** Per-citation verdicts, keyed by `chunk_id`. */
  citationVerdicts: Record<string, CitationVerdict>;
  /** Free-text describing sources the user felt were missing. */
  missingSources: string;
  /** General reviewer notes. */
  notes: string;
  /** ISO timestamp of the last feedback update. */
  updatedAt: string;
}

/**
 * A review case saved to the local workbench history.
 *
 * `materialText` is capped at storage time to keep `localStorage` within
 * quota; the full material is still sent to the backend for analysis.
 */
export interface SavedCase {
  /** Stable id (reuses `review_case_id` from the backend). */
  id: string;
  /** Trace id from the backend response. */
  traceId: string;
  /** ISO timestamp when the case was saved. */
  savedAt: string;
  /** The review question submitted by the user. */
  question: string;
  /** The material text submitted (truncated for storage). */
  materialText: string;
  /** Source name for uploaded files (otherwise null). */
  materialSource: string | null;
  /** The full backend response (facts, result, evidence, citations, chunks). */
  response: ReviewApiResponse;
  /** Human feedback, if any. */
  feedback: CaseFeedback | null;
  /** Whether the user flagged this case as a bad case. */
  isBadCase: boolean;
  /** Reason the user gave when marking it as a bad case. */
  badCaseReason: string;
}

/** A lightweight summary used to render the sidebar history list. */
export interface CaseSummary {
  id: string;
  savedAt: string;
  question: string;
  riskLevel: string;
  isBadCase: boolean;
  hasFeedback: boolean;
  conclusionUseful: boolean | null;
}

/** Default empty feedback for a freshly saved case. */
export function emptyFeedback(): CaseFeedback {
  return {
    conclusionUseful: null,
    citationVerdicts: {},
    missingSources: '',
    notes: '',
    updatedAt: '',
  };
}
