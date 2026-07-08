/**
 * CaseDetailPage — full review-case workbench view (center column).
 *
 * Renders the complete review chain for a saved case as an auditable
 * timeline, plus product-level affordances the plain workbench lacked:
 *
 *   - sticky case header with id / timestamp / risk + export buttons
 *   - pipeline stepper (事实抽取 → 查询规划 → 混合检索 → 证据自检 → 二次检索 → 结论)
 *   - material & question recap
 *   - facts grid, query plan, evidence self-check (issues + second-retrieval plan)
 *   - conclusion, trigger reasons, recommended actions, risk boundaries
 *   - expandable governed citations (CitationList) with per-citation feedback
 *   - human feedback panel (conclusion usefulness, missing sources, bad case)
 *
 * The page is read-only with respect to the backend; all interactions
 * (feedback, citation verdicts, bad-case marking) persist to the local case
 * store. Failed cases render a compact failure summary instead of the chain.
 */

import { useMemo } from 'react';
import type { ReviewApiResponse, ReviewFacts } from '../types/api';
import { isReviewFailedResponse } from '../types/api';
import type { CitationVerdict, SavedCase } from '../types/case';
import { setCitationVerdict } from '../store/caseStore';
import RiskBadge from './RiskBadge';
import CitationList from './CitationList';
import FeedbackPanel from './FeedbackPanel';
import { downloadHtml, downloadMarkdown } from '../utils/report';
import {
  EVIDENCE_ISSUE_LABELS,
  EVIDENCE_STATUS_BADGE_CLASS,
  EVIDENCE_STATUS_LABELS,
  QUERY_TYPE_LABELS,
  formatTime,
  relativeTime,
  renderBool,
  renderList,
  renderText,
  shortId,
} from '../utils/display';

interface CaseDetailPageProps {
  saved: SavedCase;
  /** Called when the user wants to start a fresh review from this case's inputs. */
  onRerun: (question: string, material: string) => void;
  /** Called when the user wants to go back to the workbench. */
  onBack: () => void;
}

/** Ordered facts shown in the 材料事实摘要 grid. */
const FACT_FIELDS: Array<{ key: string; label: string; render: (f: ReviewFacts) => string }> = [
  { key: 'business_activity', label: '业务活动', render: (f) => renderText(f.business_activity) },
  { key: 'cross_border_transfer', label: '跨境传输', render: (f) => renderBool(f.cross_border_transfer) },
  { key: 'overseas_recipient', label: '境外接收方', render: (f) => renderText(f.overseas_recipient) },
  { key: 'data_types', label: '数据类型', render: (f) => renderList(f.data_types) },
  { key: 'sensitive_personal_info', label: '敏感个人信息', render: (f) => renderBool(f.sensitive_personal_info) },
  { key: 'processing_purpose', label: '处理目的', render: (f) => renderText(f.processing_purpose) },
  { key: 'legal_basis', label: '法律依据/同意', render: (f) => renderText(f.legal_basis_or_consent) },
  { key: 'region', label: '地区', render: (f) => renderText(f.region) },
  { key: 'industry', label: '行业', render: (f) => renderText(f.industry) },
  { key: 'missing_information', label: '缺失信息', render: (f) => renderList(f.missing_information) },
];

export default function CaseDetailPage({
  saved,
  onRerun,
  onBack,
}: CaseDetailPageProps): JSX.Element {
  const response = saved.response;
  const failed = isReviewFailedResponse(response);

  const handleVerdict = (chunkId: string, verdict: CitationVerdict | null) => {
    setCitationVerdict(saved.id, chunkId, verdict);
  };

  return (
    <div className="case-detail">
      <CaseHeader
        saved={saved}
        onBack={onBack}
        onRerun={() => onRerun(saved.question, saved.materialText)}
      />

      {failed ? (
        <FailedChain response={response} />
      ) : (
        <ReviewChain
          saved={saved}
          onVerdictChange={handleVerdict}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// CaseHeader — sticky header with identity + actions
// ---------------------------------------------------------------------------

interface CaseHeaderProps {
  saved: SavedCase;
  onBack: () => void;
  onRerun: () => void;
}

function CaseHeader({ saved, onBack, onRerun }: CaseHeaderProps): JSX.Element {
  const response = saved.response;
  const failed = isReviewFailedResponse(response);
  const risk = failed ? null : response.review_result.risk_level;

  return (
    <header className="case-header card">
      <div className="case-header__top">
        <button type="button" className="btn-link case-header__back" onClick={onBack}>
          ← 返回工作台
        </button>
        <div className="case-header__actions">
          <button type="button" className="btn-secondary" onClick={onRerun}>
            以此为模板重审
          </button>
          <button type="button" className="btn-secondary" onClick={() => downloadMarkdown(saved)}>
            导出 Markdown
          </button>
          <button type="button" className="btn-primary" onClick={() => downloadHtml(saved)}>
            导出 HTML 报告
          </button>
        </div>
      </div>

      <h1 className="case-header__title">{saved.question}</h1>

      <div className="case-header__meta">
        {risk ? (
          <span className="case-header__risk">
            <RiskBadge level={risk} />
          </span>
        ) : (
          <span className="badge badge-insufficient">审查失败</span>
        )}
        <span className="case-header__meta-item">
          <span className="case-header__meta-label">案卷</span>
          <code>{shortId(saved.id)}</code>
        </span>
        {!failed ? (
          <span className="case-header__meta-item">
            <span className="case-header__meta-label">追踪</span>
            <code>{shortId(response.trace_id)}</code>
          </span>
        ) : null}
        <span className="case-header__meta-item">
          <span className="case-header__meta-label">保存于</span>
          <span title={formatTime(saved.savedAt)}>{relativeTime(saved.savedAt)}</span>
        </span>
        {saved.isBadCase ? (
          <span className="badge badge-high">坏例</span>
        ) : null}
        {saved.feedback?.conclusionUseful !== null && saved.feedback?.conclusionUseful !== undefined ? (
          <span className="badge badge-low">
            {saved.feedback.conclusionUseful ? '结论有用' : '结论无用'}
          </span>
        ) : null}
      </div>
    </header>
  );
}

// ---------------------------------------------------------------------------
// FailedChain — compact failure summary
// ---------------------------------------------------------------------------

function FailedChain({ response }: { response: Extract<ReviewApiResponse, { status: 'review_failed' }> }): JSX.Element {
  return (
    <section className="error-box" role="alert">
      <span className="error-box__mark" aria-hidden="true">!</span>
      <div>
        <div style={{ fontWeight: 700, marginBottom: '4px' }}>LLM 审查节点失败</div>
        <div style={{ wordBreak: 'break-word' }}>
          {response.failed_node}：{response.message}
        </div>
        <div style={{ marginTop: '6px', fontSize: '0.8125rem', color: '#64748b' }}>
          已重试 {response.attempts} 次 · 原因：{response.reason}
          {response.trace_id ? ` · Trace ${response.trace_id}` : ''}
        </div>
        <div className="warning-note" style={{ marginTop: '10px' }}>
          该案卷已被自动保存，你可以在左侧标记为坏例以便后续分析。
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// ReviewChain — the full pipeline timeline + detail sections
// ---------------------------------------------------------------------------

interface ReviewChainProps {
  saved: SavedCase;
  onVerdictChange: (chunkId: string, verdict: CitationVerdict | null) => void;
}

function ReviewChain({ saved, onVerdictChange }: ReviewChainProps): JSX.Element {
  const response = saved.response as Extract<ReviewApiResponse, { review_case_id: string }>;
  const result = response.review_result;
  const facts = response.review_facts;
  const selfCheck = response.evidence_self_check;
  const queries = response.retrieval_queries ?? [];
  const evidenceChunks = response.evidence_chunks ?? [];
  const verdicts = saved.feedback?.citationVerdicts ?? {};

  const evidenceCount = evidenceChunks.length;
  const citationCount = useMemo(
    () => response.citation_groups.reduce((sum, g) => sum + g.citations.length, 0),
    [response.citation_groups],
  );

  return (
    <>
      {/* Pipeline stepper */}
      <PipelineStepper
        factsCount={facts.data_types.length + (facts.cross_border_transfer ? 1 : 0)}
        queryCount={queries.length}
        evidenceCount={evidenceCount}
        selfCheckStatus={selfCheck.status}
        secondRetrieval={selfCheck.second_retrieval_triggered}
        riskLevel={result.risk_level}
      />

      {/* Question & material recap */}
      <section className="card">
        <div className="section-title">审查问题与材料</div>
        <div className="case-field">
          <div className="case-field__label">审查问题</div>
          <div className="case-field__value">{saved.question}</div>
        </div>
        <div className="case-field">
          <div className="case-field__label">
            待审查材料
            {saved.materialSource ? (
              <span className="case-field__source">（来源：{saved.materialSource}）</span>
            ) : null}
          </div>
          <pre className="case-field__material">{saved.materialText}</pre>
        </div>
      </section>

      {/* Conclusion — surfaced early for at-a-glance reading */}
      <section className="card case-conclusion">
        <div className="section-title">审查结论</div>
        <div className="case-conclusion__head">
          <RiskBadge level={result.risk_level} />
          <span className="case-conclusion__evidence">
            证据自检：
            <strong>{EVIDENCE_STATUS_LABELS[selfCheck.status]}</strong>
            {response.second_retrieval_triggered ? (
              <span className="case-conclusion__second">· 已触发二次检索</span>
            ) : null}
          </span>
        </div>
        <p className="case-conclusion__text">{result.conclusion}</p>
      </section>

      {/* Facts */}
      <section className="card">
        <div className="section-title">材料事实摘要</div>
        <div className="facts-grid">
          {FACT_FIELDS.map((f) => (
            <div className="facts-grid__item" key={f.key}>
              <span className="facts-grid__label">{f.label}</span>
              <span className="facts-grid__value">{f.render(facts)}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Query plan */}
      <section className="card">
        <div className="section-title">检索查询计划</div>
        {queries.length === 0 ? (
          <div className="state-block__hint">未生成检索查询。</div>
        ) : (
          <div className="query-plan">
            {queries.map((q, i) => (
              <div className="query-plan__item" key={q.query_id}>
                <span className="query-plan__index">{i + 1}</span>
                <span className="query-plan__type">{QUERY_TYPE_LABELS[q.query_type] ?? q.query_type}</span>
                <span className="query-plan__text">{q.text}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Evidence self-check */}
      <section className="card">
        <div className="section-title">证据自检</div>
        <div className="selfcheck">
          <div className="selfcheck__row">
            <span className="selfcheck__label">自检状态</span>
            <span className={EVIDENCE_STATUS_BADGE_CLASS[selfCheck.status]}>
              {EVIDENCE_STATUS_LABELS[selfCheck.status]}
            </span>
          </div>
          <div className="selfcheck__row">
            <span className="selfcheck__label">二次检索</span>
            <span className="selfcheck__value">
              {selfCheck.second_retrieval_triggered ? '已触发' : '未触发'}
            </span>
          </div>
          {evidenceCount > 0 ? (
            <div className="selfcheck__row">
              <span className="selfcheck__label">候选证据</span>
              <span className="selfcheck__value">{evidenceCount} 条 · 已采纳 {citationCount} 条</span>
            </div>
          ) : null}
        </div>

        {selfCheck.triggered_reasons.length > 0 ? (
          <div className="selfcheck__reasons">
            <div className="selfcheck__sublabel">触发原因</div>
            <div className="tag-list">
              {selfCheck.triggered_reasons.map((r, i) => (
                <span className="tag" key={i}>{r}</span>
              ))}
            </div>
          </div>
        ) : null}

        {selfCheck.issues.length > 0 ? (
          <div className="selfcheck__issues">
            <div className="selfcheck__sublabel">检出问题</div>
            <div className="selfcheck__issue-list">
              {selfCheck.issues.map((issue, i) => (
                <div className="selfcheck__issue" key={i}>
                  <span className="selfcheck__issue-type">
                    {EVIDENCE_ISSUE_LABELS[issue.issue_type] ?? issue.issue_type}
                  </span>
                  <span className="selfcheck__issue-desc">{issue.description}</span>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {selfCheck.second_retrieval_plan ? (
          <div className="selfcheck__plan">
            <div className="selfcheck__sublabel">二次检索计划</div>
            <div className="selfcheck__plan-grid">
              <div><strong>扩展查询</strong>：{selfCheck.second_retrieval_plan.expanded_queries.length} 条</div>
              <div><strong>增加 top_k</strong>：{selfCheck.second_retrieval_plan.increased_top_k}</div>
              <div><strong>加强 boost</strong>：{selfCheck.second_retrieval_plan.stronger_boost ? '是' : '否'}</div>
            </div>
            <div className="selfcheck__plan-reason">{selfCheck.second_retrieval_plan.reason}</div>
          </div>
        ) : null}
      </section>

      {/* Trigger reasons / actions / boundaries */}
      {result.trigger_reasons.length > 0 ? (
        <section className="card">
          <div className="section-title">触发原因</div>
          <div className="tag-list">
            {result.trigger_reasons.map((reason, i) => (
              <span className="tag" key={i}>{reason}</span>
            ))}
          </div>
        </section>
      ) : null}

      {result.recommended_actions.length > 0 ? (
        <section className="card">
          <div className="section-title">建议动作</div>
          <ol className="action-list">
            {result.recommended_actions.map((action, i) => (
              <li className="action-list__item" key={i}>{action}</li>
            ))}
          </ol>
        </section>
      ) : null}

      {result.risk_boundaries.length > 0 ? (
        <section className="card">
          <div className="section-title">风险边界</div>
          <div className="warning-list">
            {result.risk_boundaries.map((boundary, i) => (
              <div className="warning-note" key={i}>{boundary}</div>
            ))}
          </div>
        </section>
      ) : null}

      {result.missing_information.length > 0 ? (
        <section className="card">
          <div className="section-title">缺失信息</div>
          <ul className="missing-list">
            {result.missing_information.map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {/* Expandable citations with feedback */}
      <section className="card">
        <div className="section-title">可引用证据（点击展开）</div>
        <CitationList
          groups={response.citation_groups}
          evidenceChunks={evidenceChunks}
          verdicts={verdicts}
          onVerdictChange={onVerdictChange}
        />
      </section>

      {/* Human feedback */}
      <FeedbackPanel saved={saved} />
    </>
  );
}

// ---------------------------------------------------------------------------
// PipelineStepper — visual pipeline timeline
// ---------------------------------------------------------------------------

interface PipelineStepperProps {
  factsCount: number;
  queryCount: number;
  evidenceCount: number;
  selfCheckStatus: string;
  secondRetrieval: boolean;
  riskLevel: string;
}

function PipelineStepper({
  factsCount,
  queryCount,
  evidenceCount,
  selfCheckStatus,
  secondRetrieval,
  riskLevel,
}: PipelineStepperProps): JSX.Element {
  const steps: Array<{ label: string; detail: string; tone: 'done' | 'warn' | 'neutral' }> = [
    { label: '事实抽取', detail: `${factsCount} 项`, tone: 'done' },
    { label: '查询规划', detail: `${queryCount} 条查询`, tone: queryCount > 0 ? 'done' : 'neutral' },
    { label: '混合检索', detail: `${evidenceCount} 条证据`, tone: evidenceCount > 0 ? 'done' : 'neutral' },
    {
      label: '证据自检',
      detail: selfCheckStatus === 'sufficient' ? '证据充分' : selfCheckStatus === 'insufficient' ? '证据不足' : '需二次检索',
      tone: selfCheckStatus === 'sufficient' ? 'done' : selfCheckStatus === 'insufficient' ? 'warn' : 'warn',
    },
    { label: '二次检索', detail: secondRetrieval ? '已触发' : '未触发', tone: secondRetrieval ? 'warn' : 'neutral' },
    { label: '结论生成', detail: riskLabel(riskLevel), tone: riskLevel === 'high' ? 'warn' : 'done' },
  ];

  return (
    <section className="card pipeline">
      <div className="pipeline__track">
        {steps.map((step, i) => (
          <div className={'pipeline__step pipeline__step--' + step.tone} key={i}>
            <div className="pipeline__dot" aria-hidden="true">{i + 1}</div>
            <div className="pipeline__label">{step.label}</div>
            <div className="pipeline__detail">{step.detail}</div>
            {i < steps.length - 1 ? (
              <div className="pipeline__connector" aria-hidden="true" />
            ) : null}
          </div>
        ))}
      </div>
    </section>
  );
}

function riskLabel(level: string): string {
  if (level === 'high') return '高风险';
  if (level === 'medium') return '中风险';
  if (level === 'low') return '低风险';
  return '证据不足';
}
