/**
 * WorkbenchPage — main research workbench (center column).
 *
 * Lets the user enter a review question and material text, submit them for
 * analysis, and renders the structured `ReviewResponse` returned by the
 * backend: risk level, conclusion, extracted facts, trigger reasons,
 * recommended actions, risk boundaries, and applicable evidence groups.
 *
 * The question/material inputs are controlled by the parent (`App.tsx`) so
 * that the Sidebar scenario shortcuts can pre-fill the question field. The
 * parent also owns the loading / error / result state and passes the
 * `onSubmit` callback that triggers the review pipeline.
 *
 * Styling follows the Trust & Authority design system (authority navy +
 * trust gold). No purple, no gradients.
 */
import { useCallback, useRef, useState } from 'react';
import type { KeyboardEvent, ChangeEvent } from 'react';
import type {
  CitationGroup,
  CitationUsage,
  EvidenceStatus,
  ReviewApiResponse,
  ReviewFacts,
} from '../types/api';
import { isReviewFailedResponse } from '../types/api';
import RiskBadge from './RiskBadge';

export interface WorkbenchPageProps {
  /** Current review question (controlled). */
  question: string;
  /** Current material text (controlled). */
  material: string;
  /** Update the review question. */
  onQuestionChange: (value: string) => void;
  /** Update the material text. */
  onMaterialChange: (value: string) => void;
  /** Called with question + material + optional file when the user submits. */
  onSubmit: (question: string, material: string, file?: File | null) => void;
  /** True while a review request is in flight. */
  loading: boolean;
  /** The most recent review response, if any. */
  result: ReviewApiResponse | null;
  /** Error message from the last review attempt, if it failed. */
  error: string | null;
  /** Number of accumulated review records, for the empty-state hint. */
  historyCount?: number;
  /** Open the most recent result as a full case-detail view. */
  onViewDetail?: () => void;
}

/** Human-readable labels for citation usage categories. */
const USAGE_LABELS: Record<CitationUsage, string> = {
  legal_basis: '法律依据',
  conditional_basis: '条件依据',
  implementation_reference: '实施参考',
  policy_explanation: '政策释义',
};

/** Human-readable labels for evidence self-check status. */
const EVIDENCE_STATUS_LABELS: Record<EvidenceStatus, string> = {
  not_checked: '未检查',
  sufficient: '证据充分',
  needs_second_retrieval: '需二次检索',
  insufficient: '证据不足',
};

/** Render a nullable boolean as 是 / 否 / —. */
function renderBool(value: boolean | null): string {
  if (value === null || value === undefined) return '—';
  return value ? '是' : '否';
}

/** Render a nullable string, falling back to —. */
function renderText(value: string | null): string {
  return value && value.trim() ? value : '—';
}

/** Render a string array as a 、-joined list, falling back to —. */
function renderList(values: string[] | null | undefined): string {
  if (!values || values.length === 0) return '—';
  return values.join('、');
}

/** Ordered facts shown in the 材料事实摘要 grid. */
const FACT_FIELDS: Array<{
  key: string;
  label: string;
  render: (f: ReviewFacts) => string;
}> = [
  { key: 'cross_border_transfer', label: '跨境传输', render: (f) => renderBool(f.cross_border_transfer) },
  { key: 'overseas_recipient', label: '境外接收方', render: (f) => renderText(f.overseas_recipient) },
  { key: 'data_types', label: '数据类型', render: (f) => renderList(f.data_types) },
  { key: 'sensitive_personal_info', label: '敏感个人信息', render: (f) => renderBool(f.sensitive_personal_info) },
  { key: 'processing_purpose', label: '处理目的', render: (f) => renderText(f.processing_purpose) },
  { key: 'region', label: '地区', render: (f) => renderText(f.region) },
  { key: 'industry', label: '行业', render: (f) => renderText(f.industry) },
  { key: 'missing_information', label: '缺失信息', render: (f) => renderList(f.missing_information) },
];

/** A single citation group row in the 适用依据 summary. */
function CitationGroupItem({ group }: { group: CitationGroup }): JSX.Element {
  return (
    <div className="cite-group">
      <div className="cite-group__head">
        <span>{USAGE_LABELS[group.usage] ?? group.usage}</span>
        <span className="cite-group__count">{group.citations.length} 条</span>
      </div>
      {group.scope_note && (
        <div style={{ fontSize: '0.8125rem', color: '#64748b', marginTop: '2px' }}>
          {group.scope_note}
        </div>
      )}
    </div>
  );
}

export default function WorkbenchPage({
  question,
  material,
  onQuestionChange,
  onMaterialChange,
  onSubmit,
  loading,
  result,
  error,
  historyCount,
  onViewDetail,
}: WorkbenchPageProps): JSX.Element {
  // Selected file state — file is submitted directly with the review,
  // not pre-extracted. The backend saves it as part of the review case.
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Submit is allowed when not loading and there's a question plus
  // either material text or a selected file.
  const canSubmit =
    !loading &&
    question.trim() !== '' &&
    (material.trim() !== '' || selectedFile !== null);

  const handleSubmit = (): void => {
    if (!canSubmit) return;
    onSubmit(question.trim(), material.trim(), selectedFile);
  };

  // Ctrl/Cmd + Enter inside the textarea submits the form.
  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>): void => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleFileChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>): void => {
      const file = e.target.files?.[0];
      if (!file) return;
      setSelectedFile(file);
    },
    [],
  );

  const handleRemoveFile = useCallback((): void => {
    setSelectedFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, []);

  const failedResult = isReviewFailedResponse(result) ? result : null;
  const successResult = result && !isReviewFailedResponse(result) ? result : null;
  const reviewResult = successResult?.review_result ?? null;
  const facts = successResult?.review_facts ?? null;
  const citationGroups = successResult?.citation_groups ?? [];
  const evidenceSelfCheck = successResult?.evidence_self_check ?? null;

  return (
    <div className="workbench">
      {/* ---------------- Input section ---------------- */}
      <section className="card">
        <div className="workbench__field">
          <label className="workbench__label font-heading" htmlFor="wb-question">
            审查问题
          </label>
          <input
            id="wb-question"
            className="workbench__input"
            type="text"
            value={question}
            onChange={(e) => onQuestionChange(e.target.value)}
            placeholder="输入您的法律合规问题"
            disabled={loading}
          />
        </div>

        <div
          className="workbench__field"
          style={{ marginTop: 'var(--space-md)' }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
            <label className="workbench__label font-heading" htmlFor="wb-material" style={{ marginBottom: 0 }}>
              待审查材料
            </label>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              {selectedFile && (
                <span style={{ fontSize: '0.75rem', color: 'var(--color-success)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  {selectedFile.name}
                  <button
                    type="button"
                    onClick={handleRemoveFile}
                    disabled={loading}
                    style={{
                      border: 'none', background: 'none', cursor: 'pointer',
                      color: 'var(--color-danger)', fontSize: '1rem', lineHeight: 1,
                      padding: '0 2px',
                    }}
                    title="移除文件"
                    >
                    ×
                  </button>
                </span>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept=".txt,.md,.pdf,.docx,.html,.htm,.json"
                onChange={handleFileChange}
                disabled={loading}
                style={{ display: 'none' }}
                id="wb-file-upload"
              />
              <button
                type="button"
                className="btn-secondary"
                onClick={() => fileInputRef.current?.click()}
                disabled={loading}
                style={{
                  fontSize: '0.75rem',
                  padding: '4px 12px',
                  opacity: loading ? 0.6 : 1,
                  cursor: loading ? 'not-allowed' : 'pointer',
                }}
              >
                选择文件
              </button>
            </div>
          </div>
          <textarea
            id="wb-material"
            className="workbench__textarea"
            value={material}
            onChange={(e) => onMaterialChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={'粘贴待审查的材料文本，或点击右上角「选择文件」上传文档（支持 .txt .md .pdf .docx），文件将直接随审查提交'}
            disabled={loading}
          />
        </div>

        <div
          style={{
            display: 'flex',
            justifyContent: 'flex-end',
            marginTop: 'var(--space-md)',
          }}
        >
          <button
            type="button"
            className="btn-primary"
            onClick={handleSubmit}
            disabled={!canSubmit}
          >
            开始审查
          </button>
        </div>
      </section>

      {/* ---------------- Output section ---------------- */}
      {loading ? (
        <section className="card state-block">
          <span
            className="spinner spinner--dark"
            style={{ margin: '0 auto var(--space-md)' }}
            aria-hidden="true"
          />
          <div className="state-block__title">正在审查...</div>
          <div className="state-block__hint">
            系统正在进行事实抽取、混合检索与证据自检，请稍候
          </div>
        </section>
      ) : error ? (
        <section className="error-box" role="alert">
          <span className="error-box__mark" aria-hidden="true">
            !
          </span>
          <div>
            <div style={{ fontWeight: 700, marginBottom: '2px' }}>审查失败</div>
            <div style={{ wordBreak: 'break-word' }}>{error}</div>
          </div>
        </section>
      ) : failedResult ? (
        <section className="error-box" role="alert">
          <span className="error-box__mark" aria-hidden="true">
            !
          </span>
          <div>
            <div style={{ fontWeight: 700, marginBottom: '2px' }}>
              LLM 审查节点失败
            </div>
            <div style={{ wordBreak: 'break-word' }}>
              {failedResult.failed_node}：{failedResult.message}
            </div>
            <div style={{ marginTop: '6px', fontSize: '0.8125rem', color: '#64748b' }}>
              已重试 {failedResult.attempts} 次
              {failedResult.trace_id ? ` · Trace ${failedResult.trace_id}` : ''}
            </div>
          </div>
        </section>
      ) : reviewResult && facts ? (
        <section className="workbench__result">
          {/* Full-chain entry — the case-detail page shows the query plan,
              evidence chunks, self-check issues, and feedback controls. */}
          {onViewDetail ? (
            <div className="workbench__detail-entry">
              <span>
                审查已完成并保存到案卷历史。查看完整审查链路（查询计划 / 证据原文 / 自检 / 反馈 / 导出）：
              </span>
              <button
                type="button"
                className="btn-secondary"
                onClick={onViewDetail}
              >
                查看完整案卷详情 →
              </button>
            </div>
          ) : null}

          {/* (a) Risk level + evidence self-check status */}
          <div
            className="card"
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 'var(--space-sm)',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 'var(--space-md)',
                flexWrap: 'wrap',
              }}
            >
              <RiskBadge level={reviewResult.risk_level} />
              {evidenceSelfCheck && (
                <span style={{ fontSize: '0.8125rem', color: '#64748b' }}>
                  证据自检：
                  <strong style={{ color: 'var(--color-primary)' }}>
                    {EVIDENCE_STATUS_LABELS[evidenceSelfCheck.status]}
                  </strong>
                  {successResult?.second_retrieval_triggered && (
                    <span
                      style={{
                        marginLeft: 'var(--space-sm)',
                        color: 'var(--color-accent)',
                      }}
                    >
                      · 已触发二次检索
                    </span>
                  )}
                </span>
              )}
            </div>

            {/* (b) Conclusion */}
            <div
              style={{
                background: 'rgba(30, 58, 138, 0.04)',
                border: '1px solid rgba(30, 58, 138, 0.18)',
                borderRadius: 'var(--radius-md)',
                padding: 'var(--space-md)',
              }}
            >
              <div
                className="workbench__label"
                style={{ marginBottom: 'var(--space-xs)' }}
              >
                审查结论
              </div>
              <p style={{ fontSize: '0.9375rem', lineHeight: 1.6 }}>
                {reviewResult.conclusion}
              </p>
            </div>
          </div>

          {/* (c) Material facts summary */}
          <div className="card">
            <div className="section-title">材料事实摘要</div>
            <div className="facts-grid">
              {FACT_FIELDS.map((f) => (
                <div className="facts-grid__item" key={f.key}>
                  <span className="facts-grid__label">{f.label}</span>
                  <span className="facts-grid__value">{f.render(facts)}</span>
                </div>
              ))}
            </div>
          </div>

          {/* (d) Trigger reasons */}
          {reviewResult.trigger_reasons.length > 0 && (
            <div className="card">
              <div className="section-title">触发原因</div>
              <div className="tag-list">
                {reviewResult.trigger_reasons.map((reason, idx) => (
                  <span className="tag" key={idx}>
                    {reason}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* (e) Recommended actions */}
          {reviewResult.recommended_actions.length > 0 && (
            <div className="card">
              <div className="section-title">建议动作</div>
              <ol className="action-list">
                {reviewResult.recommended_actions.map((action, idx) => (
                  <li className="action-list__item" key={idx}>
                    {action}
                  </li>
                ))}
              </ol>
            </div>
          )}

          {/* (f) Risk boundaries */}
          {reviewResult.risk_boundaries.length > 0 && (
            <div className="card">
              <div className="section-title">风险边界</div>
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 'var(--space-sm)',
                }}
              >
                {reviewResult.risk_boundaries.map((boundary, idx) => (
                  <div className="warning-note" key={idx}>
                    {boundary}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* (g) Applicable evidence */}
          {citationGroups.length > 0 && (
            <div className="card">
              <div className="section-title">适用依据</div>
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 'var(--space-sm)',
                }}
              >
                {citationGroups.map((group, idx) => (
                  <CitationGroupItem group={group} key={idx} />
                ))}
              </div>
            </div>
          )}
        </section>
      ) : (
        <section className="card state-block">
          <div className="state-block__title">尚未开始审查</div>
          <div className="state-block__hint">
            在上方输入审查问题与待审查材料，点击"开始审查"获取合规分析结果
            {historyCount && historyCount > 0 ? (
              <>
                <br />
                已累计 {historyCount} 次审查记录
              </>
            ) : null}
          </div>
        </section>
      )}
    </div>
  );
}
