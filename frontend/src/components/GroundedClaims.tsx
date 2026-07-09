import { useMemo } from 'react';
import type { GroundedClaim, RetrievalHit } from '../types/api';
import { shortId } from '../utils/display';

interface GroundedClaimsProps {
  claims: GroundedClaim[] | undefined;
  evidenceChunks: RetrievalHit[] | undefined;
  compact?: boolean;
}

const CIRCLED_NUMBERS = ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨', '⑩'];

export default function GroundedClaims({
  claims,
  evidenceChunks,
  compact = false,
}: GroundedClaimsProps): JSX.Element | null {
  const chunkMap = useMemo(() => {
    const map = new Map<string, RetrievalHit>();
    (evidenceChunks ?? []).forEach((chunk) => map.set(chunk.chunk_id, chunk));
    return map;
  }, [evidenceChunks]);

  if (!claims || claims.length === 0) return null;

  return (
    <div className={'cite-cards' + (compact ? ' cite-cards--compact' : '')}>
      <div className="cite-cards__header">引用条款</div>
      {claims.map((claim, index) => {
        const marker = CIRCLED_NUMBERS[index] ?? String(index + 1);
        // Show the first supporting chunk as the primary cited article.
        const primaryChunkId = claim.supporting_chunk_ids[0];
        const chunk = primaryChunkId ? chunkMap.get(primaryChunkId) : undefined;
        const extraChunks = claim.supporting_chunk_ids
          .slice(1)
          .map((id) => chunkMap.get(id))
          .filter((c): c is RetrievalHit => c !== undefined);

        return (
          <article
            className="cite-card"
            key={`${claim.text}-${index}`}
            id={`cite-card-${index}`}
          >
            <div className="cite-card__badge">{marker}</div>
            <div className="cite-card__body">
              <div className="cite-card__title">
                {chunk?.citation_label || chunk?.title || '引用条款'}
              </div>
              {chunk && (
                <blockquote className="cite-card__text">
                  {chunk.text}
                </blockquote>
              )}
              <div className="cite-card__meta">
                <span className="cite-card__source">
                  {chunk?.title || '未知来源'}
                </span>
                {chunk?.article_no && (
                  <span className="cite-card__article">{chunk.article_no}</span>
                )}
                <a
                  className="cite-card__link"
                  href={`#cite-marker-${index}`}
                  title="跳转到正文引用位置"
                >
                  回到正文
                </a>
              </div>
              {extraChunks.length > 0 && (
                <div className="cite-card__extras">
                  <span className="cite-card__extras-label">同时引用：</span>
                  {extraChunks.map((c) => (
                    <span className="cite-card__extra" key={c.chunk_id}>
                      {c.citation_label || c.title}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </article>
        );
      })}
    </div>
  );
}

export function cssId(value: string): string {
  return value.replace(/[^a-zA-Z0-9_-]/g, '-');
}
