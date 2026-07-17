import { useMemo } from 'react';
import type { GroundedClaim, RetrievalHit } from '../types/api';
import { shortId } from '../utils/display';
import MarkdownText from './MarkdownText';

interface GroundedClaimsProps {
  claims: GroundedClaim[] | undefined;
  evidenceChunks: RetrievalHit[] | undefined;
  compact?: boolean;
  selectedEvidenceId?: string | null;
  onEvidenceSelect?: (chunkId: string, label: string) => void;
}

export default function GroundedClaims({
  claims,
  evidenceChunks,
  compact = false,
  selectedEvidenceId = null,
  onEvidenceSelect,
}: GroundedClaimsProps): JSX.Element | null {
  const chunkMap = useMemo(() => {
    const map = new Map<string, RetrievalHit>();
    (evidenceChunks ?? []).forEach((chunk) => map.set(chunk.chunk_id, chunk));
    return map;
  }, [evidenceChunks]);

  if (!claims || claims.length === 0) return null;

  return (
    <section
      className={'grounded-claims' + (compact ? ' grounded-claims--compact' : '')}
      aria-label="关键判断与引用依据"
    >
      <div className="grounded-claims__header">
        <span>关键判断与引用</span>
        <span>点击依据可在右栏核对原文</span>
      </div>
      {claims.map((claim, index) => {
        return (
          <article
            className="grounded-claim"
            key={`${claim.text}-${index}`}
          >
            <div className="grounded-claim__text">
              <span className="grounded-claim__index" aria-hidden="true">
                {index + 1}
              </span>
              <MarkdownText variant="inline">{claim.text}</MarkdownText>
            </div>
            <div className="grounded-claim__refs" aria-label={`判断 ${index + 1} 的引用依据`}>
              {claim.supporting_chunk_ids.map((chunkId) => {
                const chunk = chunkMap.get(chunkId);
                const label = chunk?.citation_label || chunk?.title || `依据 ${shortId(chunkId)}`;
                const className =
                  'grounded-claim__ref' +
                  (selectedEvidenceId === chunkId ? ' is-active' : '');

                return onEvidenceSelect ? (
                  <button
                    type="button"
                    className={className}
                    key={chunkId}
                    onClick={() => onEvidenceSelect(chunkId, label)}
                    aria-pressed={selectedEvidenceId === chunkId}
                    aria-label={`在引用依据栏查看：${label}`}
                  >
                    {label}
                  </button>
                ) : (
                  <a
                    className={className}
                    key={chunkId}
                    href={`#evidence-${cssId(chunkId)}`}
                    aria-label={`在引用依据栏查看：${label}`}
                  >
                    {label}
                  </a>
                );
              })}
            </div>
          </article>
        );
      })}
    </section>
  );
}

export function cssId(value: string): string {
  return value.replace(/[^a-zA-Z0-9_-]/g, '-');
}
