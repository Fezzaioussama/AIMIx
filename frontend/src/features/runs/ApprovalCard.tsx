import { useState } from 'react';

import type { RunApproval } from '../../core/api/types';
import { useNow } from '../../core/hooks/useNow';
import { ArgumentList } from './ArgumentList';
import { argumentRows, formatTimeLeft, toolLabel } from './approvalFormat';
import { RUN_BUTTON } from './runButtons';

type Choice = 'approve' | 'decline';

interface ApprovalCardProps {
  approval: RunApproval;
  /** Who asks: the step's name, and its agent's role when it has one. */
  askedBy: string;
  /** An answer is on its way. */
  busy?: boolean;
  /** Without both handlers the request is shown but cannot be answered here. */
  onApprove?: () => void;
  onDecline?: () => void;
}

/** Where the tool comes from, as a phrase; built-in tools need no source. */
function fromSource(source: string): string {
  return source === 'AIMIx' ? '' : ` from ${source}`;
}

/**
 * One tool call waiting for the run's owner: which step wants it, the tool in
 * plain words, what it will use, the time left, and Approve or Decline. Doing
 * nothing counts as a decline once the time is up.
 */
export function ApprovalCard({ approval, askedBy, busy, onApprove, onDecline }: ApprovalCardProps) {
  const [choice, setChoice] = useState<Choice | null>(null);
  const now = useNow(true);
  const headingId = `approval-${approval.id}`;
  const answer = (next: Choice, send: () => void) => {
    setChoice(next);
    send();
  };
  const pending = busy ? choice : null;

  return (
    <section
      aria-labelledby={headingId}
      className="rounded-2xl border border-amber-400/40 bg-amber-400/[0.06] p-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
        <p className="text-xs font-semibold tracking-widest text-amber-300 uppercase">
          Needs your OK
        </p>
        <p className="text-xs text-slate-300 tabular-nums">
          {formatTimeLeft(Date.parse(approval.expires_at) - now)}
        </p>
      </div>
      <h3 id={headingId} className="mt-1 text-base font-semibold break-words text-slate-50">
        Allow “{toolLabel(approval.tool_name, approval.tool_source)}”?
      </h3>
      <p className="mt-1 text-sm break-words text-slate-300">
        {askedBy} wants to use this tool{fromSource(approval.tool_source)}.
      </p>
      {approval.tool_description && (
        <p className="mt-1 text-sm break-words text-slate-400">{approval.tool_description}</p>
      )}
      <ArgumentList rows={argumentRows(approval.arguments)} />
      {approval.arguments_truncated && (
        <p className="mt-2 text-xs text-slate-400">
          Long values are shortened here. The tool uses them in full.
        </p>
      )}
      {onApprove && onDecline ? (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => answer('approve', onApprove)}
            disabled={busy}
            className={`${RUN_BUTTON.resume} min-h-10`}
          >
            {pending === 'approve' ? 'Approving…' : 'Approve'}
          </button>
          <button
            type="button"
            onClick={() => answer('decline', onDecline)}
            disabled={busy}
            className={`${RUN_BUTTON.stop} min-h-10`}
          >
            {pending === 'decline' ? 'Declining…' : 'Decline'}
          </button>
          <span className="text-xs text-slate-400">No answer counts as a decline.</span>
        </div>
      ) : (
        <p className="mt-3 text-xs text-slate-400">Answer it from the run in Runs.</p>
      )}
    </section>
  );
}
