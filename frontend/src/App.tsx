/**
 * App — top-level shell for the LawAgent frontend.
 *
 * Owns the global page state and review history, and lays out the
 * three-column structure described in the design spec:
 *
 *   [ Sidebar 240px ] [ Center (flex) ] [ EvidenceDossier 360px ]
 *
 * The right-hand EvidenceDossier is only meaningful on the workbench
 * page, so it is hidden entirely when the user is on the eval page.
 *
 * Responsive behavior:
 *   - screens < 1200px: right dossier panel is hidden
 *   - screens < 768px : single column (sidebar collapses into a compact
 *                       top navigation bar)
 */

import { useCallback, useState } from 'react'
import type { ReviewApiResponse } from './types/api'
import { ApiError, submitReview } from './api/client'
import Sidebar from './components/Sidebar'
import EvidenceDossier from './components/EvidenceDossier'
import WorkbenchPage from './components/WorkbenchPage'
import EvalPage from './components/EvalPage'

/** Top-level page the user is currently viewing. */
type Page = 'workbench' | 'eval'

export default function App(): JSX.Element {
  // ---- Global app state -------------------------------------------------
  const [currentPage, setCurrentPage] = useState<Page>('workbench')
  const [reviewHistory, setReviewHistory] = useState<ReviewApiResponse[]>([])
  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)

  // ---- Workbench form state (lifted so the Sidebar scenario shortcuts
  //      can pre-fill the input) -----------------------------------------
  const [question, setQuestion] = useState<string>('')
  const [material, setMaterial] = useState<string>('')
  const [currentResult, setCurrentResult] = useState<ReviewApiResponse | null>(
    null,
  )

  // ---- Handlers ---------------------------------------------------------
  const handleSubmit = useCallback(
    async (q: string, m: string, file?: File | null) => {
      setLoading(true)
      setError(null)
      try {
        const response = await submitReview(q, m, file)
        setReviewHistory((prev) => [response, ...prev])
        setCurrentResult(response)
      } catch (err) {
        const message =
          err instanceof ApiError
            ? err.message
            : err instanceof Error
              ? err.message
              : '提交研究请求时发生未知错误'
        setError(message)
      } finally {
        setLoading(false)
      }
    },
    [],
  )

  const handleScenarioClick = useCallback((scenario: string) => {
    // A scenario shortcut always takes the user to the workbench and
    // fills the question field so they can review and submit.
    setCurrentPage('workbench')
    setQuestion(scenario)
  }, [])

  const handlePageChange = useCallback((page: Page) => {
    setCurrentPage(page)
  }, [])

  // The dossier is only relevant on the workbench page.
  const showDossier = currentPage === 'workbench'

  // ---- Render -----------------------------------------------------------
  return (
    <div className="app-shell">
      <Sidebar
        currentPage={currentPage}
        onPageChange={handlePageChange}
        onScenarioClick={handleScenarioClick}
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

        {currentPage === 'workbench' ? (
          <WorkbenchPage
            question={question}
            material={material}
            onQuestionChange={setQuestion}
            onMaterialChange={setMaterial}
            onSubmit={handleSubmit}
            loading={loading}
            error={error}
            result={currentResult}
            historyCount={reviewHistory.length}
          />
        ) : (
          <EvalPage />
        )}
      </main>

      {showDossier && <EvidenceDossier reviewResponse={currentResult} />}
    </div>
  )
}
