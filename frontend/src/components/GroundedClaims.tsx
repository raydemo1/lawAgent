import { useMemo } from 'react';
import type { GroundedClaim, RetrievalHit } from '../types/api';
import { shortId } from '../utils/display';

interface GroundedClaimsProps {
  claims: GroundedClaim[] | undefined;
  evidenceChunks: RetrievalHit[] | undefined;
  compact?: boolean;
}

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
    <div className={'grounded-claims' + (compact ? ' grounded-claims--compact' : '')}>
      {claims.map((claim, index) => (
        <article className="grounded-claim" key={`${claim.text}-${index}`}>
          <div className="grounded-claim__text">
            <span className="grounded-claim__index">{index + 1}</span>
            <span>
              <HighlightedClaimText text={claim.text} />
              {claim.supporting_chunk_ids.map((chunkId) => {
                const chunk = chunkMap.get(chunkId);
                return (
                  <a
                    className="grounded-claim__marker"
                    href={`#evidence-${cssId(chunkId)}`}
                    title={chunk ? `${chunk.title} · ${chunk.chunk_id}` : chunkId}
                    key={chunkId}
                  >
                    [{shortId(chunkId)}]
                  </a>
                );
              })}
            </span>
          </div>
          <div className="grounded-claim__refs" aria-label="支持该结论的证据 chunk">
            {claim.supporting_chunk_ids.map((chunkId) => {
              const chunk = chunkMap.get(chunkId);
              return (
                <span
                  className="grounded-claim__ref"
                  title={chunk ? `${chunk.title} · ${chunk.chunk_id}` : chunkId}
                  key={chunkId}
                >
                  {chunk ? shortId(chunk.chunk_id) : shortId(chunkId)}
                </span>
              );
            })}
          </div>
        </article>
      ))}
    </div>
  );
}

function HighlightedClaimText({ text }: { text: string }): JSX.Element {
  const pattern = /(《[^》]+》第[一二三四五六七八九十百零〇\d]+(?:条|款|项)|数据出境安全评估|个人信息出境标准合同|个人信息保护认证|单独同意)/g;
  const parts = text.split(pattern);
  return (
    <>
      {parts.map((part, index) =>
        isHighlightTerm(part) ? (
          <strong className="grounded-claim__emphasis" key={`${part}-${index}`}>
            {part}
          </strong>
        ) : (
          <span key={`${part}-${index}`}>{part}</span>
        ),
      )}
    </>
  );
}

function isHighlightTerm(value: string): boolean {
  return /^(《[^》]+》第[一二三四五六七八九十百零〇\d]+(?:条|款|项)|数据出境安全评估|个人信息出境标准合同|个人信息保护认证|单独同意)$/.test(value);
}

export function cssId(value: string): string {
  return value.replace(/[^a-zA-Z0-9_-]/g, '-');
}
