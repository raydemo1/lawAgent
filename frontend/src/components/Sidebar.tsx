/**
 * Sidebar — left navigation column (240px).
 *
 * Contains:
 *   - Brand area (LawAgent + Chinese subtitle)
 *   - Primary navigation (研究工作台 / 评测看板)
 *   - Scenario shortcuts — preset questions that pre-fill the workbench
 *   - Case history — reopen past reviews, search, delete, see risk/bad-case
 *     badges at a glance. Clicking a case opens the case detail page.
 *   - Footer disclaimer
 *
 * The case history is sourced from the local case store and updates live
 * whenever a new review is saved or feedback changes.
 */

import { useMemo, useState } from 'react';
import { deleteCase, useCaseStore } from '../store/caseStore';
import { isReviewFailedResponse } from '../types/api';
import { relativeTime, truncate } from '../utils/display';

export type Page = 'workbench' | 'eval' | 'case-detail';

interface SidebarProps {
  /** Currently active top-level page. */
  currentPage: Page;
  /** Switch the active page. */
  onPageChange: (page: Page) => void;
  /** Pre-fill the workbench question with a preset scenario. */
  onScenarioClick: (scenario: string) => void;
  /** Open a saved case in the detail view. */
  onOpenCase: (caseId: string) => void;
  /** Id of the case currently shown in the detail view (for highlight). */
  activeCaseId?: string | null;
}

/** Preset questions shown as scenario shortcuts. */
const SCENARIOS: string[] = [
  '这个场景是否需要数据出境安全评估？',
  '数据出境安全评估的申报条件是什么？',
  '智能网联汽车数据出境有什么特殊要求？',
  '上海自贸区数据出境负面清单有什么要求？',
];

const RISK_DOT_CLASS: Record<string, string> = {
  high: 'risk-dot risk-dot--high',
  medium: 'risk-dot risk-dot--medium',
  low: 'risk-dot risk-dot--low',
  insufficient_evidence: 'risk-dot risk-dot--insufficient',
  failed: 'risk-dot risk-dot--insufficient',
};

export default function Sidebar({
  currentPage,
  onPageChange,
  onScenarioClick,
  onOpenCase,
  activeCaseId,
}: SidebarProps): JSX.Element {
  const cases = useCaseStore();
  const [query, setQuery] = useState('');

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return cases;
    return cases.filter(
      (c) => c.question.toLowerCase().includes(q) || c.id.toLowerCase().includes(q),
    );
  }, [cases, query]);

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

      {/* ---- Case history ---- */}
      <div className="sidebar-section sidebar-history">
        <div className="sidebar-section-label">
          案卷历史
          <span className="sidebar-history__count">{cases.length}</span>
        </div>

        {cases.length > 0 ? (
          <input
            type="search"
            className="sidebar-history__search"
            placeholder="搜索问题或编号"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="搜索案卷历史"
          />
        ) : null}

        <div className="sidebar-history__list">
          {cases.length === 0 ? (
            <div className="sidebar-history__empty">
              尚无审查记录。提交一次审查后会在此显示。
            </div>
          ) : filtered.length === 0 ? (
            <div className="sidebar-history__empty">没有匹配的案卷。</div>
          ) : (
            filtered.map((c) => {
              const risk = isReviewFailedResponse(c.response)
                ? 'failed'
                : c.response.review_result.risk_level;
              const isActive = c.id === activeCaseId;
              return (
                <div
                  key={c.id}
                  className={
                    'history-item' + (isActive ? ' is-active' : '')
                  }
                >
                  <button
                    type="button"
                    className="history-item__main"
                    onClick={() => onOpenCase(c.id)}
                    title={c.question}
                  >
                    <div className="history-item__top">
                      <span className={RISK_DOT_CLASS[risk] ?? RISK_DOT_CLASS.insufficient_evidence} aria-hidden="true" />
                      <span className="history-item__question">
                        {truncate(c.question, 28)}
                      </span>
                    </div>
                    <div className="history-item__meta">
                      <span>{relativeTime(c.savedAt)}</span>
                      {c.isBadCase ? <span className="history-item__badge">坏例</span> : null}
                      {c.feedback?.conclusionUseful === false ? (
                        <span className="history-item__badge history-item__badge--warn">无用</span>
                      ) : null}
                      {c.feedback?.conclusionUseful === true ? (
                        <span className="history-item__badge history-item__badge--ok">有用</span>
                      ) : null}
                    </div>
                  </button>
                  <button
                    type="button"
                    className="history-item__delete"
                    title="删除该案卷"
                    aria-label="删除该案卷"
                    onClick={() => {
                      if (window.confirm('确定删除该案卷记录？此操作不可撤销。')) {
                        deleteCase(c.id);
                      }
                    }}
                  >
                    ×
                  </button>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* ---- Footer ---- */}
      <div className="sidebar-footer">
        LawAgent · 法律合规研究
        <br />
        仅供研究参考，不构成正式法律意见
      </div>
    </aside>
  );
}
