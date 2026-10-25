import type { ReactNode } from 'react';

import { PRIMARY_BUTTON, SECONDARY_BUTTON } from '../pipelines/buttonStyles';
import { PipelineGraph } from '../pipelines/PipelineGraph';
import { ChangeList } from '../pipelines/RevisionReview';
import type { RevisionProposal } from '../pipelines/useRevisePipeline';
import { Bubble, Working } from './Bubble';
import type { MessageContext, ViewProps } from './messageContext';
import type { ProposalMessage, ProposalState } from './missionMessages';
import { countOf } from './teamBrief';

const STOPPED = 'Stopped. Ask again whenever you like.';
const STALE = 'The team changed after you asked, so I set that proposal aside. Ask again.';

/** How a settled answer reads; a pending one that is no longer live has expired. */
const SETTLED: Record<Exclude<ProposalState, 'pending'>, (message: ProposalMessage) => ReactNode> =
  {
    applied: (message) => (
      <>
        <p>Done. I applied {countOf(message.changes.length, 'change')}:</p>
        <div className="mt-2">
          <ChangeList changes={message.changes} />
        </div>
      </>
    ),
    discarded: (message) =>
      message.changes.length > 0
        ? 'Discarded. The team stays as it was.'
        : 'Nothing changed. The team stays as it was.',
    failed: (message) => message.error,
    stopped: () => STOPPED,
    expired: () => 'That proposal is no longer available. Ask again if you still want the change.',
  };

interface ReviewProps {
  proposal: RevisionProposal;
  onApply: () => void;
  onDiscard: () => void;
}

/** The proposed changes in plain words, a preview of the new team, then Apply or Discard. */
function Review({ proposal, onApply, onDiscard }: ReviewProps) {
  const count = proposal.changes.length;
  if (count === 0) {
    return (
      <Bubble>
        <p>Nothing to change: I left the team as it is. Try saying it another way.</p>
        <button type="button" onClick={onDiscard} className={`mt-3 ${SECONDARY_BUTTON}`}>
          Close
        </button>
      </Bubble>
    );
  }
  return (
    <Bubble>
      <p className="mb-2">Here’s what I would change ({countOf(count, 'change')}):</p>
      <ChangeList changes={proposal.changes} />
      <details className="mt-3 rounded-xl border border-white/10 bg-slate-950/40 px-3 py-2">
        <summary className="cursor-pointer text-sm font-medium text-slate-200 select-none">
          Preview the new team
        </summary>
        <div className="mt-3">
          <PipelineGraph steps={proposal.pipeline.steps} inputs={proposal.pipeline.inputs} />
        </div>
      </details>
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" onClick={onApply} className={PRIMARY_BUTTON}>
          Apply
        </button>
        <button type="button" onClick={onDiscard} className={SECONDARY_BUTTON}>
          Discard
        </button>
      </div>
    </Bubble>
  );
}

/** The answer still in play: working, failed, ready to review, or set aside. */
function LiveProposal({ context }: { context: MessageContext }) {
  const { proposals, focusComposer } = context;
  const { revision } = proposals;
  if (revision.busy) {
    return (
      <Bubble>
        <Working onStop={revision.cancel}>Working on your change…</Working>
      </Bubble>
    );
  }
  if (revision.error) return <Bubble tone="error">{revision.error}</Bubble>;
  if (revision.proposal === null) return <Bubble>{revision.stale ? STALE : STOPPED}</Bubble>;
  const settle = (action: () => void) => () => {
    action();
    focusComposer();
  };
  return (
    <Review
      proposal={revision.proposal}
      onApply={settle(proposals.apply)}
      onDiscard={settle(proposals.discard)}
    />
  );
}

/** AIMIx's answer to a change request: live while it is the open one, else its outcome. */
export function ProposalMessageView({ message, context }: ViewProps<'proposal'>) {
  if (message.state === 'pending' && message.id === context.proposals.activeId) {
    return <LiveProposal context={context} />;
  }
  const state = message.state === 'pending' ? 'expired' : message.state;
  return <Bubble tone={state === 'failed' ? 'error' : 'info'}>{SETTLED[state](message)}</Bubble>;
}
