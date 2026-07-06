/**
 * Sidebar — left navigation column (240px).
 *
 * Contains:
 *   - Brand area (LawAgent + Chinese subtitle in EB Garamond)
 *   - Primary navigation (研究工作台 / 评测看板)
 *   - Scenario shortcuts — preset questions that pre-fill the workbench
 *     input when clicked.
 */

interface SidebarProps {
  /** Currently active top-level page. */
  currentPage: 'workbench' | 'eval'
  /** Switch the active page. */
  onPageChange: (page: 'workbench' | 'eval') => void
  /** Pre-fill the workbench question with a preset scenario. */
  onScenarioClick: (scenario: string) => void
}

/** Preset questions shown as scenario shortcuts. */
const SCENARIOS: string[] = [
  '这个场景是否需要数据出境安全评估？',
  '数据出境安全评估的申报条件是什么？',
  '智能网联汽车数据出境有什么特殊要求？',
  '上海自贸区数据出境负面清单有什么要求？',
]

export default function Sidebar({
  currentPage,
  onPageChange,
  onScenarioClick,
}: SidebarProps): JSX.Element {
  return (
    <aside className="app-sidebar sidebar">
      {/* ---- Brand ---- */}
      <div className="sidebar-brand">
        <div className="sidebar-brand-title">LawAgent</div>
        <div className="sidebar-brand-subtitle">法律合规研究工作台</div>
      </div>

      {/* ---- Primary navigation ---- */}
      <nav className="sidebar-section" aria-label="主导航">
        <div className="sidebar-section-label">导航</div>
        <div className="sidebar-nav">
          <button
            type="button"
            className={
              'sidebar-nav-item' +
              (currentPage === 'workbench' ? ' is-active' : '')
            }
            onClick={() => onPageChange('workbench')}
            aria-current={currentPage === 'workbench' ? 'page' : undefined}
          >
            <svg
              className="sidebar-nav-item-icon"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={1.8}
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M14 3v4a1 1 0 0 0 1 1h4" />
              <path d="M17 21H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 5v11a2 2 0 0 1-2 2z" />
              <path d="M9 13h6M9 17h4" />
            </svg>
            <span className="font-heading">研究工作台</span>
          </button>

          <button
            type="button"
            className={
              'sidebar-nav-item' +
              (currentPage === 'eval' ? ' is-active' : '')
            }
            onClick={() => onPageChange('eval')}
            aria-current={currentPage === 'eval' ? 'page' : undefined}
          >
            <svg
              className="sidebar-nav-item-icon"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={1.8}
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M3 3v18h18" />
              <path d="M7 14v4M12 9v9M17 5v13" />
            </svg>
            <span className="font-heading">评测看板</span>
          </button>
        </div>
      </nav>

      {/* ---- Scenario shortcuts ---- */}
      <div className="sidebar-section">
        <div className="sidebar-section-label">快捷场景</div>
        <div className="sidebar-scenarios">
          {SCENARIOS.map((scenario) => (
            <button
              key={scenario}
              type="button"
              className="sidebar-scenario"
              onClick={() => onScenarioClick(scenario)}
            >
              {scenario}
            </button>
          ))}
        </div>
      </div>

      {/* ---- Footer ---- */}
      <div className="sidebar-footer">
        LawAgent · 法律合规研究
        <br />
        仅供研究参考，不构成正式法律意见
      </div>
    </aside>
  )
}
