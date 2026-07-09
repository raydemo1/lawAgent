/**
 * CitationList — expandable, governable citation browser.
 *
 * Renders the citation groups returned by a review response. Each citation
 * row collapses to a one-line summary (label + role + cite-eligibility chip)
 * and expands on click to reveal the underlying clause chunk text, source
 * URL, retriever/score, and per-citation feedback controls (correct / wrong).
 *
 * The chunk text is looked up from `evidence_chunks` (keyed by `chunk_id`),
 * which the backend now returns alongside the citation groups. When a chunk
 * is missing (e.g. older saved cases), the expansion gracefully shows a
 * "条文本不可用" note.
 *
 * Feedback state is owned by the parent via `verdicts` / `onVerdictChange`
 * so it persists with the saved case.
 */

import { useMemo, useState } from 'react';
import type {
  Citation,
  CitationGroup,
  RetrievalHit,
  SourceEvidencePacket,
} from '../types/api';
import type { CitationVerdict } from '../types/case';
import {
  CITATION_ROLE_LABELS,
  USAGE_LABELS,
  USAGE_ORDER,
  shortId,
} from '../utils/display';

interface CitationListProps {
  groups: CitationGroup[];
  evidenceChunks: RetrievalHit[] | undefined;
  sourceEvidencePackets: SourceEvidencePacket[];
  /** Per-chunk verdicts from the saved case feedback. */
  verdicts: Record<string, CitationVerdict>;
  /** Called when the user toggles a citation verdict. */
  onVerdictChange: (chunkId: string, verdict: CitationVerdict | null) => void;
  /** Disable feedback controls (e.g. for failed cases). */
  feedbackDisabled?: boolean;
}

function chunksById(hits: RetrievalHit[] | undefined): Map<string, RetrievalHit> {
  const map = new Map<string, RetrievalHit>();
  if (hits) for (const h of hits) map.set(h.chunk_id, h);
  return map;
}

export default function CitationList({
  groups,
  evidenceChunks,
  sourceEvidencePackets,
  verdicts,
  onVerdictChange,
  feedbackDisabled = false,
}: CitationListProps): JSX.Element {
  const chunkMap = useMemo(() => chunksById(evidenceChunks), [evidenceChunks]);
  const ordered = useMemo(
    () =>
      [...groups].sort(
        (a, b) => USAGE_ORDER.indexOf(a.usage) - USAGE_ORDER.indexOf(b.usage),
      ),
    [groups],
  );

  if (ordered.length === 0 && sourceEvidencePackets.length === 0) {
    return (
      <div className="state-block">
        <div className="state-block__title">暂无可引用证据</div>
        <div className="state-block__hint">本次审查未生成可引用证据。</div>
      </div>
    );
  }

  return (
    <div className="cite-list">
      {sourceEvidencePackets.length > 0 ? (
        <SourcePacketList packets={sourceEvidencePackets} />
      ) : null}

      {ordered.map((group) => (
        <section className="cite-list__group" key={group.usage}>
          <div className="cite-list__group-head">
            <span className="cite-list__group-label">
              {USAGE_LABELS[group.usage]}
            </span>
            <span className="cite-list__group-count">{group.citations.length} 条</span>
          </div>
          {group.scope_note ? (
            <div className="cite-list__group-scope">{group.scope_note}</div>
          ) : null}
          <div className="cite-list__items">
            {group.citations.map((citation, idx) => (
              <CitationRow
                key={citation.chunk_id}
                citation={citation}
                index={idx + 1}
                chunk={chunkMap.get(citation.chunk_id)}
                verdict={verdicts[citation.chunk_id] ?? null}
                onVerdictChange={onVerdictChange}
                feedbackDisabled={feedbackDisabled}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function SourcePacketList({
  packets,
}: {
  packets: SourceEvidencePacket[];
}): JSX.Element {
  return (
    <section className="source-packets">
      <div className="source-packets__head">
        <span className="source-packets__title">来源证据包</span>
        <span className="source-packets__count">{packets.length} 个来源</span>
      </div>
      <div className="source-packets__list">
        {packets.map((packet, index) => (
          <SourcePacketRow packet={packet} index={index + 1} key={packet.source_id} />
        ))}
      </div>
    </section>
  );
}

function SourcePacketRow({
  packet,
  index,
}: {
  packet: SourceEvidencePacket;
  index: number;
}): JSX.Element {
  const [open, setOpen] = useState(index <= 2);
  const supportingCount = packet.supporting_chunks.length;
  const neighborCount = packet.neighbor_chunks.length;
  return (
    <div className={'source-packet' + (open ? ' is-open' : '')}>
      <button
        type="button"
        className="source-packet__head"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="cite-row__chevron" aria-hidden="true">
          {open ? '▾' : '▸'}
        </span>
        <span className="cite-row__index">{index}</span>
        <span className="source-packet__title">{packet.title}</span>
        <span className="source-packet__meta">
          支撑 {supportingCount} · 邻居 {neighborCount}
        </span>
      </button>
      {open ? (
        <div className="source-packet__body">
          <PacketChunk label="代表 chunk" chunk={packet.representative_chunk} />
          {packet.supporting_chunks.map((chunk, idx) => (
            <PacketChunk label={`同源支撑 ${idx + 1}`} chunk={chunk} key={chunk.chunk_id} />
          ))}
          {packet.neighbor_chunks.map((chunk, idx) => (
            <PacketChunk label={`邻居上下文 ${idx + 1}`} chunk={chunk} key={chunk.chunk_id} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function PacketChunk({
  label,
  chunk,
}: {
  label: string;
  chunk: RetrievalHit;
}): JSX.Element {
  return (
    <article className="packet-chunk">
      <div className="packet-chunk__head">
        <span className="packet-chunk__label">{label}</span>
        <span className="packet-chunk__meta">
          <code>{shortId(chunk.chunk_id)}</code>
          <code>{chunk.score.toFixed(4)}</code>
          {chunk.can_cite_clause ? (
            <span className="cite-chip cite-chip--cite">可引用</span>
          ) : (
            <span className="cite-chip cite-chip--ref">参考</span>
          )}
        </span>
      </div>
      <pre className="packet-chunk__text">{chunk.text}</pre>
    </article>
  );
}

// ---------------------------------------------------------------------------
// CitationRow — a single expandable citation
// ---------------------------------------------------------------------------

interface CitationRowProps {
  citation: Citation;
  index: number;
  chunk: RetrievalHit | undefined;
  verdict: CitationVerdict | null;
  onVerdictChange: (chunkId: string, verdict: CitationVerdict | null) => void;
  feedbackDisabled: boolean;
}

function CitationRow({
  citation,
  index,
  chunk,
  verdict,
  onVerdictChange,
  feedbackDisabled,
}: CitationRowProps): JSX.Element {
  const [open, setOpen] = useState(false);
  const label = citation.citation_label ?? citation.title;
  const hasChunkText = Boolean(chunk && chunk.text);

  return (
    <div className={'cite-row' + (open ? ' is-open' : '')}>
      <button
        type="button"
        className="cite-row__head"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="cite-row__chevron" aria-hidden="true">
          {open ? '▾' : '▸'}
        </span>
        <span className="cite-row__index">{index}</span>
        <span className="cite-row__label">{label}</span>
        <span className="cite-row__chips">
          <span className="cite-chip cite-chip--role">
            {CITATION_ROLE_LABELS[citation.citation_role]}
          </span>
          {citation.can_cite_clause ? (
            <span className="cite-chip cite-chip--cite">可引用条文</span>
          ) : (
            <span className="cite-chip cite-chip--ref">仅作参考</span>
          )}
        </span>
      </button>

      {open ? (
        <div className="cite-row__body">
          {/* Source URL */}
          {citation.source_url ? (
            <div className="cite-row__field">
              <span className="cite-row__field-label">来源</span>
              <a
                className="cite-row__link"
                href={citation.source_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                {citation.source_url}
              </a>
            </div>
          ) : (
            <div className="cite-row__field">
              <span className="cite-row__field-label">来源</span>
              <span className="cite-row__muted">无来源链接</span>
            </div>
          )}

          {/* Retrieval metadata */}
          {chunk ? (
            <div className="cite-row__meta">
              <span>
                <span className="cite-row__meta-label">检索器</span>
                <code>{chunk.retriever}</code>
              </span>
              <span>
                <span className="cite-row__meta-label">评分</span>
                <code>{chunk.score.toFixed(4)}</code>
              </span>
              <span>
                <span className="cite-row__meta-label">chunk</span>
                <code>{shortId(chunk.chunk_id)}</code>
              </span>
              {chunk.matched_query_type ? (
                <span>
                  <span className="cite-row__meta-label">匹配查询</span>
                  <code>{chunk.matched_query_type}</code>
                </span>
              ) : null}
            </div>
          ) : null}

          {/* Chunk text */}
          <div className="cite-row__field">
            <span className="cite-row__field-label">条文内容</span>
            {hasChunkText ? (
              <pre className="cite-row__chunk">{chunk!.text}</pre>
            ) : (
              <div className="cite-row__muted">
                该引用的原始条款文本不可用（可能来自旧版案卷）。
              </div>
            )}
          </div>

          {/* Per-citation feedback */}
          {!feedbackDisabled ? (
            <div className="cite-row__feedback">
              <span className="cite-row__field-label">引用评价</span>
              <div className="cite-row__verdicts">
                <button
                  type="button"
                  className={
                    'cite-verdict' +
                    (verdict === 'correct' ? ' is-active is-correct' : '')
                  }
                  onClick={() =>
                    onVerdictChange(
                      citation.chunk_id,
                      verdict === 'correct' ? null : 'correct',
                    )
                  }
                >
                  正确
                </button>
                <button
                  type="button"
                  className={
                    'cite-verdict' +
                    (verdict === 'wrong' ? ' is-active is-wrong' : '')
                  }
                  onClick={() =>
                    onVerdictChange(
                      citation.chunk_id,
                      verdict === 'wrong' ? null : 'wrong',
                    )
                  }
                >
                  错误
                </button>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
