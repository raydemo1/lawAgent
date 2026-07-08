/**
 * FeedbackPanel — human-in-the-loop review feedback for a saved case.
 *
 * Lets the reviewer record:
 *   - overall conclusion usefulness (有用 / 无用)
 *   - free-text "缺少来源" describing evidence gaps
 *   - general notes
 *   - mark the whole case as a bad case (with a reason) for later eval
 *     improvement
 *
 * Per-citation verdicts live inside `CitationList`; this panel covers the
 * case-level feedback. All changes are persisted to the case store
 * immediately via the supplied callbacks so feedback survives a refresh.
 */

import { useState } from 'react';
import type { SavedCase } from '../types/case';
import {
  setBadCase,
  setConclusionUseful,
  setFeedbackText,
} from '../store/caseStore';

interface FeedbackPanelProps {
  saved: SavedCase;
}

export default function FeedbackPanel({ saved }: FeedbackPanelProps): JSX.Element {
  const feedback = saved.feedback;
  const [badReasonDraft, setBadReasonDraft] = useState(saved.badCaseReason);
  const [missingDraft, setMissingDraft] = useState(feedback?.missingSources ?? '');
  const [notesDraft, setNotesDraft] = useState(feedback?.notes ?? '');
  const [showBadForm, setShowBadForm] = useState(false);

  const conclusionUseful = feedback?.conclusionUseful ?? null;

  return (
    <div className="card feedback">
      <div className="section-title">人工反馈</div>

      {/* Conclusion usefulness */}
      <div className="feedback__block">
        <div className="feedback__label">结论评价</div>
        <div className="feedback__toggle-group">
          <button
            type="button"
            className={
              'feedback-toggle' +
              (conclusionUseful === true ? ' is-active is-useful' : '')
            }
            onClick={() =>
              setConclusionUseful(saved.id, conclusionUseful === true ? null : true)
            }
          >
            <span aria-hidden="true">👍</span> 有用
          </button>
          <button
            type="button"
            className={
              'feedback-toggle' +
              (conclusionUseful === false ? ' is-active is-useless' : '')
            }
            onClick={() =>
              setConclusionUseful(saved.id, conclusionUseful === false ? null : false)
            }
          >
            <span aria-hidden="true">👎</span> 无用
          </button>
        </div>
      </div>

      {/* Missing sources */}
      <div className="feedback__block">
        <div className="feedback__label">缺少来源</div>
        <textarea
          className="feedback__textarea"
          placeholder="描述你认为本次审查缺少了哪些法规/条款来源"
          value={missingDraft}
          onChange={(e) => setMissingDraft(e.target.value)}
          onBlur={() => setFeedbackText(saved.id, 'missingSources', missingDraft)}
          rows={2}
        />
      </div>

      {/* Notes */}
      <div className="feedback__block">
        <div className="feedback__label">备注</div>
        <textarea
          className="feedback__textarea"
          placeholder="其他补充说明"
          value={notesDraft}
          onChange={(e) => setNotesDraft(e.target.value)}
          onBlur={() => setFeedbackText(saved.id, 'notes', notesDraft)}
          rows={3}
        />
      </div>

      {/* Bad case */}
      <div className="feedback__block">
        <div className="feedback__label">坏例标记</div>
        {saved.isBadCase ? (
          <div className="bad-case-banner">
            <div className="bad-case-banner__head">
              <span>已标记为坏例</span>
              <button
                type="button"
                className="btn-link"
                onClick={() => {
                  setBadCase(saved.id, false);
                  setShowBadForm(false);
                }}
              >
                取消标记
              </button>
            </div>
            {saved.badCaseReason ? (
              <div className="bad-case-banner__reason">{saved.badCaseReason}</div>
            ) : null}
          </div>
        ) : showBadForm ? (
          <div className="bad-case-form">
            <textarea
              className="feedback__textarea"
              placeholder="为什么这是一个坏例？（如：检索召回缺失、结论错误、引用不相关）"
              value={badReasonDraft}
              onChange={(e) => setBadReasonDraft(e.target.value)}
              rows={2}
            />
            <div className="bad-case-form__actions">
              <button
                type="button"
                className="btn-primary btn-danger"
                onClick={() => {
                  setBadCase(saved.id, true, badReasonDraft.trim());
                  setShowBadForm(false);
                }}
              >
                确认保存为坏例
              </button>
              <button
                type="button"
                className="btn-secondary"
                onClick={() => {
                  setShowBadForm(false);
                  setBadReasonDraft('');
                }}
              >
                取消
              </button>
            </div>
          </div>
        ) : (
          <button
            type="button"
            className="btn-secondary btn-bad-case"
            onClick={() => setShowBadForm(true)}
          >
            保存为坏例
          </button>
        )}
      </div>

      {/* Feedback summary */}
      {feedback && feedback.updatedAt ? (
        <div className="feedback__updated">
          反馈已于 {feedback.updatedAt.replace('T', ' ').slice(0, 16)} 更新
        </div>
      ) : null}
    </div>
  );
}
