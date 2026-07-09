import { useMemo } from 'react';
import type { GroundedClaim, RetrievalHit } from '../types/api';
import { shortId } from '../utils/display';

interface GroundedClaimsProps {
  claims: GroundedClaim[];
  evidenceChunks: RetrievalHit[];
}

export default function GroundedClaims({
  claims,
  evidenceChunks,
}: GroundedClaimsProps): JSX.Element | null {
  const chunkMap = useMemo(() => {
    const map = new Map<string, RetrievalHit>();
    evidenceChunks.forEach((chunk) => map.set(chunk.chunk_id, chunk));
    return map;
  }, [evidenceChunks]);

  if (claims.length === 0) return null;

  return (
    <div className="grounded-claims">
      {claims.map((claim, index) => (
        <article className="grounded-claim" key={`${claim.text}-${index}`}>
          <div className="grounded-claim__text">
            <span className="grounded-claim__index">{index + 1}</span>
            <span>{claim.text}</span>
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
