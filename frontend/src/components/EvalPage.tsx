/**
 * EvalPage — center column placeholder for the evaluation dashboard.
 *
 * The full dashboard (per-mode metrics, bad cases, retrieval comparison)
 * will be implemented in a later step. This placeholder keeps the App
 * shell compilable and communicates the planned content, reusing the
 * existing `.state-block` component class from global.css.
 */

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

export default function EvalPage(): JSX.Element {
  return (
    <div className="workbench" style={{ maxWidth: 820, margin: '0 auto' }}>
      <header style={headerStyle}>
        <h1>评测看板</h1>
        <p style={headerDescStyle}>
          基于黄金评测集，对比不同检索策略（关键词 / 混合）的召回率、
          MRR、引用违规与坏案例表现。
        </p>
      </header>

      <div className="card state-block">
        <div className="state-block__title">评测看板即将上线</div>
        <div className="state-block__hint">
          详细的检索模式对比、召回指标与坏案例分析面板正在开发中。
          届时可在此查看 keyword 与 hybrid 模式的 Recall@3 / Recall@5 /
          MRR@10、引用违规统计与二次检索准确率。
        </div>
      </div>
    </div>
  )
}
