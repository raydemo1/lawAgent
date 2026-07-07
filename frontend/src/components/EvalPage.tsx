import { useCallback, useEffect, useState } from 'react'
import { ApiError, getLatestEval, runEvaluation } from '../api/client'
import type { CaseMetricResult, EvalSummary, ModeMetrics } from '../types/api'

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
  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)

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
      const next = await runEvaluation({ modes: ['service'], top_k: 10 })
      setSummary(next)
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : '运行 service 评测失败'
      setError(message)
    } finally {
      setLoading(false)
    }
  }, [])

  const serviceMetrics = summary?.mode_metrics.service ?? null
  const badCases = summary?.bad_cases ?? []

  return (
    <div className="workbench" style={{ maxWidth: 900, margin: '0 auto' }}>
      <header style={headerStyle}>
        <h1>评测看板</h1>
        <p style={headerDescStyle}>
          当前前端只运行真实 service 检索评测：Elasticsearch + pgvector +
          RRF 融合，不展示 local baseline 作为主结果。
        </p>
      </header>

      <div className="card" style={{ display: 'flex', justifyContent: 'space-between', gap: 'var(--space-md)', alignItems: 'center', flexWrap: 'wrap' }}>
        <div>
          <div className="section-title" style={{ marginBottom: '2px' }}>
            Service 评测
          </div>
          <div style={{ color: '#64748b', fontSize: '0.875rem' }}>
            {summary
              ? `生成时间：${summary.generated_at} · Corpus：${summary.chunks_path}`
              : '尚无缓存结果，点击运行评测。'}
          </div>
        </div>
        <button
          type="button"
          className="btn-primary"
          onClick={handleRun}
          disabled={loading}
        >
          {loading ? '评测运行中...' : '运行 service 评测'}
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
          <div className="state-block__title">正在运行真实 service 评测</div>
          <div className="state-block__hint">
            将连接 Elasticsearch 与 pgvector，完整跑完黄金评测集。
          </div>
        </section>
      ) : serviceMetrics ? (
        <>
          <section className="card">
            <div className="section-title">核心指标</div>
            <div style={gridStyle}>
              {metricItems(serviceMetrics).map(([label, value]) => (
                <MetricCard key={label} label={label} value={value} />
              ))}
            </div>
          </section>

          <section className="card">
            <div className="section-title">坏例</div>
            {badCases.length === 0 ? (
              <div className="state-block__hint">本次 service 评测没有坏例。</div>
            ) : (
              badCases.map((item) => (
                <BadCaseRow key={item.case_id} item={item} />
              ))
            )}
          </section>
        </>
      ) : (
        <section className="card state-block">
          <div className="state-block__title">暂无 service 评测结果</div>
          <div className="state-block__hint">
            点击上方按钮运行真实 service 评测后，将展示 Recall、MRR、引用违规和坏例。
          </div>
        </section>
      )}
    </div>
  )
}
