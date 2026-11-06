import { useState } from 'react';

import type { RunApproval } from '../../core/api/types';
import { FOCUS_RING } from '../../core/ui/focus';
import { ArgumentList } from './ArgumentList';
import { argumentRows } from './approvalFormat';
import { QuestionCard } from './QuestionCard';
import { RUN_BUTTON } from './runButtons';
import { TimeLeft } from './TimeLeft';
import { approvalHeading, fromSource, isPlainAsk } from './toolWords';

type Choice = 'approve' | 'decline';

interface ApprovalCardProps {
  approval: RunApproval;
  /** Who asks: the step's name, and its agent's role when it has one. */
  askedBy: string;
  /** An answer is on its way. */
  busy?: boolean;
  /** Without the handlers the request is shown but cannot be answered here. */
  onApprove?: () => void;
  onDecline?: () => void;
  /** For a question (`kind: "question"`): send what the person answered. */
  onAnswer?: (text: string) => void;
}

type AnswerProps = Pick<ApprovalCardProps, 'busy' | 'onApprove' | 'onDecline'>;

/** Approve and Decline, the one pressed reading "Approving…" or "Declining…" meanwhile. */
function Answers({ busy, onApprove, onDecline }: AnswerProps) {
  const [choice, setChoice] = useState<Choice | null>(null);
  if (!onApprove || !onDecline) {
    return <p className="mt-3 text-xs text-slate-400">Answer it from the run in Runs.</p>;
  }
  const answer = (next: Choice, send: () => void) => {
    setChoice(next);
    send();
  };
  const pending = busy ? choice : null;
  return (
    <div className="mt-4 flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={() => answer('approve', onApprove)}
        disabled={busy}
        className={RUN_BUTTON.resume}
      >
        {pending === 'approve' ? 'Approving…' : 'Approve'}
      </button>
      <button
        type="button"
        onClick={() => answer('decline', onDecline)}
        disabled={busy}
        className={RUN_BUTTON.stop}
      >
        {pending === 'decline' ? 'Declining…' : 'Decline'}
      </button>
    </div>
  );
}

/**
 * One tool call waiting for the run's owner: what it asks in plain words (a
 * built-in tool's request, or the tool's name), which step wants it, what it will
 * use, Approve or Decline, and the time left. Doing nothing counts as a decline
 * once the time is up. No motion on purpose: PendingApprovals keeps the focus.
 */
export function ApprovalCard({
  approval,
  askedBy,
  busy,
  onApprove,
  onDecline,
  onAnswer,
}: ApprovalCardProps) {
  const headingId = `approval-${approval.id}`;
  if (approval.kind === 'question') {
    return (
      <QuestionCard
        approval={approval}
        askedBy={askedBy}
        headingId={headingId}
        busy={busy}
        onAnswer={onAnswer}
        onSkip={onDecline}
      />
    );
  }
  const plain = isPlainAsk(approval);

  return (
    <section
      aria-labelledby={headingId}
      className="rounded-2xl border border-amber-400/40 bg-amber-400/[0.06] p-4"
    >
      {/* The jump target of "Review the request", hence focusable. */}
      <h3
        id={headingId}
        tabIndex={-1}
        className={`scroll-mt-[calc(var(--sticky-top,0px)+1rem)] rounded text-base font-semibold text-balance break-words text-slate-50 ${FOCUS_RING}`}
      >
        {approvalHeading(approval)}
      </h3>
      <p className="mt-1 text-sm break-words text-slate-300">
        {plain
          ? `${askedBy} wants your OK first.`
          : `${askedBy} wants to use this tool${fromSource(approval.tool_source)}.`}
      </p>
      {!plain && approval.tool_description && (
        <p className="mt-1 text-sm break-words text-slate-400">{approval.tool_description}</p>
      )}
      <ArgumentList rows={argumentRows(approval.arguments)} />
      {approval.arguments_truncated && (
        <p className="mt-2 text-xs text-slate-400">
          Long values are shortened here. The tool uses them in full.
        </p>
      )}
      <Answers busy={busy} onApprove={onApprove} onDecline={onDecline} />
      <TimeLeft expiresAt={approval.expires_at} consequence="No answer counts as a decline." />
    </section>
  );
}
