/**
 * App — top-level shell for the LawAgent frontend.
 *
 * Owns the global page state and review history, and lays out the
 * three-column structure described in the design spec:
 *
 *   [ Sidebar 240px ] [ Center (flex) ] [ EvidenceDossier 360px ]
 *
 * Pages:
 *   - workbench    — enter a new review question + material and submit
 *   - case-detail  — full auditable review chain for a saved case
 *   - eval         — evaluation dashboard
 *
 * The right-hand EvidenceDossier is meaningful on the workbench and
 * case-detail pages; it is hidden on the eval page.
 *
 * Review history is persisted client-side via the case store
 * (`store/caseStore.ts`), so past reviews survive a page refresh and can be
 * reopened, annotated with feedback, exported, or flagged as bad cases.
 *
 * Responsive behavior:
 *   - screens < 1200px: right dossier panel is hidden
 *   - screens < 768px : single column (sidebar collapses into a compact
 *                       top navigation bar)
 */

import { useCallback, useMemo, useState } from 'react';
import type { ReviewApiResponse } from './types/api';
import { ApiError, submitReview } from './api/client';
import Sidebar from './components/Sidebar';
import type { Page } from './components/Sidebar';
import EvidenceDossier from './components/EvidenceDossier';
import WorkbenchPage from './components/WorkbenchPage';
import EvalPage from './components/EvalPage';
import CaseDetailPage from './components/CaseDetailPage';
import { saveCase, useCaseStore } from './store/caseStore';

export default function App(): JSX.Element {
  // ---- Global app state -------------------------------------------------
  const [currentPage, setCurrentPage] = useState<Page>('workbench');
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // ---- Workbench form state (lifted so the Sidebar scenario shortcuts
  //      can pre-fill the input, and so "rerun from case" can populate it) -
  const [question, setQuestion] = useState<string>('');
  const [material, setMaterial] = useState<string>('');
  const [currentResult, setCurrentResult] = useState<ReviewApiResponse | null>(
    null,
  );

  // ---- Case-detail state ------------------------------------------------
  const [activeCaseId, setActiveCaseId] = useState<string | null>(null);
  // Subscribe to the case store so the active case stays in sync with any
  // feedback / bad-case / verdict mutations performed inside the detail page.
  const cases = useCaseStore();
  const activeSavedCase = useMemo(
    () => (activeCaseId ? cases.find((c) => c.id === activeCaseId) ?? null : null),
    [cases, activeCaseId],
  );

  // ---- Handlers ---------------------------------------------------------
  const handleSubmit = useCallback(
    async (q: string, m: string, file?: File | null) => {
      setLoading(true);
      setError(null);
      try {
        const response = await submitReview(q, m, file);
        // Persist the submission to the local case store so it appears in
        // the sidebar history and can be reopened / annotated / exported.
        const saved = saveCase(response, q, m, file?.name ?? null);
        setCurrentResult(response);
        setActiveCaseId(saved.id);
        setCurrentPage('case-detail');
      } catch (err) {
        const message =
          err instanceof ApiError
            ? err.message
            : err instanceof Error
              ? err.message
              : '提交研究请求时发生未知错误';
        setError(message);
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  const handleScenarioClick = useCallback((scenario: string) => {
    // A scenario shortcut always takes the user to the workbench and
    // fills the question field so they can review and submit.
    setCurrentPage('workbench');
    setQuestion(scenario);
  }, []);

  const handlePageChange = useCallback((page: Page) => {
    setCurrentPage(page);
  }, []);

  const handleOpenCase = useCallback((caseId: string) => {
    const saved = cases.find((c) => c.id === caseId);
    if (!saved) return;
    setActiveCaseId(caseId);
    setCurrentResult(saved.response);
    setCurrentPage('case-detail');
  }, [cases]);

  const handleRerunFromCase = useCallback((q: string, m: string) => {
    // Pre-fill the workbench form from an existing case so the user can
    // iterate on the same question/material.
    setQuestion(q);
    setMaterial(m);
    setActiveCaseId(null);
    setCurrentResult(null);
    setError(null);
    setCurrentPage('workbench');
  }, []);

  const handleBackToWorkbench = useCallback(() => {
    setCurrentPage('workbench');
  }, []);

  const handleViewDetail = useCallback(() => {
    // Open the most recently saved case (newest first) in the detail view.
    const latest = cases[0];
    if (!latest) return;
    setActiveCaseId(latest.id);
    setCurrentResult(latest.response);
    setCurrentPage('case-detail');
  }, [cases]);

  // The dossier is relevant on the workbench and case-detail pages.
  const showDossier = currentPage === 'workbench' || currentPage === 'case-detail';

  // ---- Render -----------------------------------------------------------
  return (
    <div className="app-shell">
      <Sidebar
        currentPage={currentPage}
        onPageChange={handlePageChange}
        onScenarioClick={handleScenarioClick}
        onOpenCase={handleOpenCase}
        activeCaseId={activeCaseId}
      />

      <main className="app-center">
        {/* Compact navigation shown only on small screens (<768px). */}
        <div className="app-mobile-nav">
          <span className="app-mobile-brand">LawAgent</span>
          <div className="app-mobile-tabs">
            <button
              type="button"
              className={
                'app-mobile-tab' +
                (currentPage === 'workbench' ? ' is-active' : '')
              }
              onClick={() => handlePageChange('workbench')}
            >
              <span className="font-heading">研究工作台</span>
            </button>
            <button
              type="button"
              className={
                'app-mobile-tab' +
                (currentPage === 'eval' ? ' is-active' : '')
              }
              onClick={() => handlePageChange('eval')}
            >
              <span className="font-heading">评测看板</span>
            </button>
          </div>
        </div>

        {currentPage === 'case-detail' && activeSavedCase ? (
          <CaseDetailPage
            saved={activeSavedCase}
            onRerun={handleRerunFromCase}
            onBack={handleBackToWorkbench}
          />
        ) : currentPage === 'case-detail' && !activeSavedCase ? (
          // The active case was deleted or not found — fall back to workbench.
          <WorkbenchPage
            question={question}
            material={material}
            onQuestionChange={setQuestion}
            onMaterialChange={setMaterial}
            onSubmit={handleSubmit}
            loading={loading}
            error={error}
            result={currentResult}
            historyCount={cases.length}
            onViewDetail={handleViewDetail}
          />
        ) : currentPage === 'workbench' ? (
          <WorkbenchPage
            question={question}
            material={material}
            onQuestionChange={setQuestion}
            onMaterialChange={setMaterial}
            onSubmit={handleSubmit}
            loading={loading}
            error={error}
            result={currentResult}
            historyCount={cases.length}
            onViewDetail={handleViewDetail}
          />
        ) : (
          <EvalPage />
        )}
      </main>

      {showDossier ? <EvidenceDossier reviewResponse={currentResult} /> : null}
    </div>
  );
}
