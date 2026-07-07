import { useCallback, useEffect, useState } from 'react'
import { ApiError, getEvalStatus, getLatestEval, runEvaluation } from '../api/client'
import type {
  CaseMetricResult,
  EvalJobResponse,
  EvalRetrievalMode,
  EvalReviewMode,
  EvalSummary,
  ModeMetrics,
} from '../types/api'

const headerStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 'var(--space-xs)',
}

const headerDescStyle: React.CSSProperties = {
  color: '#64748b',
  fontSize: '0.9375rem',
  lineHeight: 1.6,
}

const gridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
  gap: 'var(--space-sm)',
}

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

function metricItems(metrics: ModeMetrics): Array<[string, string]> {
  return [
    ['Recall@3', pct(metrics.mean_recall_at_3)],
    ['Recall@5', pct(metrics.mean_recall_at_5)],
    ['MRR@10', metrics.mean_mrr_at_10.toFixed(4)],
    ['拒答准确率', pct(metrics.abstention_accuracy)],
    ['二次检索', pct(metrics.second_retrieval_accuracy)],
    ['引用违规', String(metrics.total_citation_violations)],
    ['坏例', `${metrics.bad_case_count} / ${metrics.total_cases}`],
  ]
}

function evalMetricKey(retrievalMode: EvalRetrievalMode, reviewMode: EvalReviewMode): string {
  return `retrieval=${retrievalMode},review=${reviewMode}`
}

function modeLabel(value: EvalRetrievalMode | EvalReviewMode): string {
  if (value === 'service') return 'Service'
  if (value === 'llm') return 'LLM'
  return 'Local'
}

function ModeToggle<T extends EvalRetrievalMode | EvalReviewMode>({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: T
  options: T[]
  onChange: (value: T) => void
}): JSX.Element {
  return (
    <div>
      <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#64748b', marginBottom: 6 }}>
        {label}
      </div>
      <div
        style={{
          display: 'inline-grid',
          gridTemplateColumns: `repeat(${options.length}, minmax(72px, 1fr))`,
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-sm)',
          overflow: 'hidden',
          background: '#fff',
        }}
      >
        {options.map((option) => {
          const active = value === option
          return (
            <button
              key={option}
              type="button"
              onClick={() => onChange(option)}
              aria-pressed={active}
              style={{
                border: 0,
                borderRight: option === options[options.length - 1] ? 0 : '1px solid var(--color-border)',
                padding: '8px 12px',
                background: active ? '#0f172a' : '#fff',
                color: active ? '#fff' : '#334155',
                fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              {modeLabel(option)}
            </button>
          )
        })}
      </div>
    </div>
  )
}

function MetricCard({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div
      style={{
        border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius-md)',
        padding: 'var(--space-md)',
        background: 'rgba(248, 250, 252, 0.78)',
      }}
    >
      <div style={{ fontSize: '0.75rem', color: '#64748b' }}>{label}</div>
      <div style={{ fontSize: '1.25rem', fontWeight: 700, marginTop: '2px' }}>
        {value}
      </div>
    </div>
  )
}

function BadCaseRow({ item }: { item: CaseMetricResult }): JSX.Element {
  return (
    <div
      style={{
        borderTop: '1px solid var(--color-border)',
        padding: 'var(--space-sm) 0',
      }}
    >
      <div style={{ fontWeight: 700 }}>{item.case_id}</div>
      <div style={{ color: '#64748b', fontSize: '0.8125rem', marginTop: '2px' }}>
        {item.bad_reasons.join('、') || '未标记原因'}
      </div>
      {item.missing_sources.length > 0 ? (
        <div style={{ color: '#b45309', fontSize: '0.8125rem', marginTop: '2px' }}>
          missing: {item.missing_sources.join('、')}
        </div>
      ) : null}
    </div>
  )
}

export default function EvalPage(): JSX.Element {
  const [summary, setSummary] = useState<EvalSummary | null>(null)
  const [job, setJob] = useState<EvalJobResponse | null>(null)
  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)
  const [retrievalMode, setRetrievalMode] = useState<EvalRetrievalMode>('service')
  const [reviewMode, setReviewMode] = useState<EvalReviewMode>('llm')

  useEffect(() => {
    let active = true
    getLatestEval()
      .then((latest) => {
        if (active) setSummary(latest)
      })
      .catch((err) => {
        if (!active) return
        setError(err instanceof Error ? err.message : '读取评测结果失败')
      })
    return () => {
      active = false
    }
  }, [])

  const handleRun = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const next = await runEvaluation({
        retrieval_mode: retrievalMode,
        review_mode: reviewMode,
        top_k: 10,
      })
      setJob(next)
      if (next.status === 'failed') {
        throw new ApiError(500, next.message ?? 'service 评测失败', '/api/eval/run')
      }
      if (next.status === 'succeeded') {
        const latest = await getLatestEval()
        setSummary(latest)
        return
      }
      let latestJob = next
      while (latestJob.status === 'running') {
        await new Promise((resolve) => window.setTimeout(resolve, 2000))
        latestJob = await getEvalStatus()
        setJob(latestJob)
      }
      if (latestJob.status === 'failed') {
        throw new ApiError(
          500,
          latestJob.message ?? 'service 评测失败',
          '/api/eval/status',
        )
      }
      const latest = await getLatestEval()
      setSummary(latest)
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : '运行评测失败'
      setError(message)
    } finally {
      setLoading(false)
    }
  }, [retrievalMode, reviewMode])

  const activeMetricKey = evalMetricKey(retrievalMode, reviewMode)
  const activeMetrics = summary?.mode_metrics[activeMetricKey] ?? null
  const badCases = summary?.bad_cases ?? []
  const runningHint = job?.status === 'running' && job.started_at
    ? `任务 ${job.job_id ?? ''} · started ${job.started_at}`
    : `检索：${modeLabel(retrievalMode)} · 审查：${modeLabel(reviewMode)}。`

  return (
    <div className="workbench" style={{ maxWidth: 900, margin: '0 auto' }}>
      <header style={headerStyle}>
        <h1>评测看板</h1>
        <p style={headerDescStyle}>
          评测入口只保留两个选择：检索使用 Service 或 Local，审查步骤使用 LLM 或 Local。
        </p>
      </header>

      <div className="card" style={{ display: 'flex', justifyContent: 'space-between', gap: 'var(--space-md)', alignItems: 'center', flexWrap: 'wrap' }}>
        <div>
          <div className="section-title" style={{ marginBottom: '2px' }}>
            当前评测配置
          </div>
          <div style={{ color: '#64748b', fontSize: '0.875rem' }}>
            {summary
              ? `生成时间：${summary.generated_at} · Corpus：${summary.chunks_path}`
              : '尚无缓存结果，点击运行评测。'}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 'var(--space-sm)', flexWrap: 'wrap' }}>
          <ModeToggle
            label="检索"
            value={retrievalMode}
            options={['service', 'local']}
            onChange={setRetrievalMode}
          />
          <ModeToggle
            label="审查"
            value={reviewMode}
            options={['llm', 'local']}
            onChange={setReviewMode}
          />
        </div>
        <button
          type="button"
          className="btn-primary"
          onClick={handleRun}
          disabled={loading}
        >
          {loading ? '评测运行中...' : '运行评测'}
        </button>
      </div>

      {error ? (
        <section className="error-box" role="alert">
          <span className="error-box__mark" aria-hidden="true">!</span>
          <div>
            <div style={{ fontWeight: 700, marginBottom: '2px' }}>评测失败</div>
            <div style={{ wordBreak: 'break-word' }}>{error}</div>
          </div>
        </section>
      ) : null}

      {loading ? (
        <section className="card state-block">
          <span
            className="spinner spinner--dark"
            style={{ margin: '0 auto var(--space-md)' }}
            aria-hidden="true"
          />
          <div className="state-block__title">正在运行评测</div>
          <div className="state-block__hint">
            {runningHint}
          </div>
        </section>
      ) : activeMetrics ? (
        <>
          <section className="card">
            <div className="section-title">核心指标</div>
            <div style={gridStyle}>
              {metricItems(activeMetrics).map(([label, value]) => (
                <MetricCard key={label} label={label} value={value} />
              ))}
            </div>
          </section>

          <section className="card">
            <div className="section-title">坏例</div>
            {badCases.length === 0 ? (
              <div className="state-block__hint">本次评测没有坏例。</div>
            ) : (
              badCases.map((item) => (
                <BadCaseRow key={item.case_id} item={item} />
              ))
            )}
          </section>
        </>
      ) : (
        <section className="card state-block">
          <div className="state-block__title">暂无当前配置的评测结果</div>
          <div className="state-block__hint">
            点击上方按钮运行评测后，将展示 Recall、MRR、引用违规和坏例。
          </div>
        </section>
      )}
    </div>
  )
}
