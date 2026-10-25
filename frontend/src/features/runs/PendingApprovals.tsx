import { useEffect, useRef } from 'react';

import type { Run } from '../../core/api/types';
import { stepLabel } from '../pipelines/stages';
import { ApprovalCard } from './ApprovalCard';

interface PendingApprovalsProps {
  run: Run;
  /** Answer a request by its id; without both, the requests show but cannot be answered here. */
  onApprove?: (approvalId: number) => void;
  onDecline?: (approvalId: number) => void;
  /** An answer is on its way. */
  busy?: boolean;
}

/** The step and its agent's role, e.g. "Draft email (Writer)", as the card says who asks. */
function askedBy(run: Run, stepOrder: number): string {
  const step = run.definition.steps.find((item) => item.order === stepOrder);
  const name = stepLabel({ order: stepOrder, title: step?.title ?? '' });
  return step?.role.trim() ? `${name} (${step.role.trim()})` : name;
}

/**
 * The tool calls a run waits on, one card each, right under its status bar.
 * Renders no card while none is waiting. A screen that shows a run passes the
 * answers from `useRun` (`live.approve`, `live.decline`).
 */
export function PendingApprovals({ run, onApprove, onDecline, busy }: PendingApprovalsProps) {
  const waiting = run.pending_approvals;
  const anchor = useRef<HTMLDivElement>(null);
  const shown = useRef(waiting.length);

  // Answering removes the focused button along with its card. Keep the keyboard where
  // it was, instead of letting focus fall back to the top of the page.
  useEffect(() => {
    if (waiting.length < shown.current && document.activeElement === document.body) {
      anchor.current?.focus({ preventScroll: true });
    }
    shown.current = waiting.length;
  }, [waiting.length]);

  const answerable = onApprove !== undefined && onDecline !== undefined;
  return (
    <div ref={anchor} tabIndex={-1} className="outline-none">
      {waiting.length > 0 && (
        <section aria-label="Actions waiting for your approval" className="mt-4 space-y-3">
          <p className="sr-only" aria-live="polite">
            {waiting.length === 1
              ? '1 action is waiting for your approval.'
              : `${waiting.length} actions are waiting for your approval.`}
          </p>
          {waiting.map((approval) => (
            <ApprovalCard
              key={approval.id}
              approval={approval}
              askedBy={askedBy(run, approval.step_order)}
              busy={busy}
              onApprove={answerable ? () => onApprove(approval.id) : undefined}
              onDecline={answerable ? () => onDecline(approval.id) : undefined}
            />
          ))}
        </section>
      )}
    </div>
  );
}
