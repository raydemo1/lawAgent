/**
 * RiskBadge — small reusable risk-level indicator.
 *
 * Renders the standard `.badge` pill (defined in `styles/global.css`) with the
 * tone-on-tint color matching the backend `RiskLevel` enum. Used by the
 * WorkbenchPage to surface a review's overall risk level at a glance.
 */
import type { RiskLevel } from '../types/api';

export interface RiskBadgeProps {
  level: RiskLevel;
}

interface RiskConfig {
  /** Chinese label shown inside the badge. */
  label: string;
  /** Global CSS class controlling the badge color. */
  className: string;
}

const RISK_CONFIG: Record<RiskLevel, RiskConfig> = {
  high: { label: '高风险', className: 'badge badge-high' },
  medium: { label: '中风险', className: 'badge badge-medium' },
  low: { label: '低风险', className: 'badge badge-low' },
  insufficient_evidence: {
    label: '证据不足',
    className: 'badge badge-insufficient',
  },
};

export default function RiskBadge({ level }: RiskBadgeProps): JSX.Element {
  const config = RISK_CONFIG[level] ?? RISK_CONFIG.insufficient_evidence;
  return <span className={config.className}>{config.label}</span>;
}
