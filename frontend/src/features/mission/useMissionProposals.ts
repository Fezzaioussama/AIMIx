import { useState } from 'react';

import type { Pipeline } from '../../core/api/types';
import { useMountedRef } from '../../core/hooks/useMountedRef';
import { useRevisePipeline, type RevisePipeline } from '../pipelines/useRevisePipeline';
import {
  note,
  pendingProposal,
  settleProposal,
  you,
  type ProposalOutcome,
} from './missionMessages';
import type { Conversation } from './useMissionConversation';
import type { MissionTeam } from './useMissionTeam';

/** Revising needs a pipeline; before there is a team this empty one stands in. */
export const NO_TEAM: Pipeline = { name: '', inputs: [], steps: [] };

export interface MissionProposals {
  revision: RevisePipeline;
  /** The answer the live proposal belongs to, if one is open. */
  activeId: string | null;
  /** Sends a change request; the answer follows the live proposal. */
  request: (instruction: string) => void;
  apply: () => void;
  discard: () => void;
  /** Keeps the open proposal's outcome, e.g. before the person asks to run. */
  settle: () => void;
}

/** What an open proposal becomes when the conversation moves on without applying it. */
export function outcomeOf(revision: RevisePipeline): ProposalOutcome {
  if (revision.error) return { state: 'failed', error: revision.error };
  if (revision.proposal) return { state: 'discarded', changes: revision.proposal.changes };
  return { state: revision.stale ? 'expired' : 'stopped' };
}

/**
 * Change requests in the conversation, over useRevisePipeline: each request gets an
 * answer that shows the live proposal, and keeps the outcome once it is settled.
 * Applying replaces the team; a mission already saved is saved again at once, so the
 * team it reopens with is the one the conversation describes.
 */
export function useMissionProposals(team: MissionTeam, conversation: Conversation) {
  const revision = useRevisePipeline(team.pipeline ?? NO_TEAM);
  const [activeId, setActiveId] = useState<string | null>(null);
  const mounted = useMountedRef();
  const { append, update } = conversation;

  function close(outcome: ProposalOutcome) {
    if (activeId !== null) update(activeId, settleProposal(outcome));
    revision.discard();
    setActiveId(null);
  }

  async function saveApplied() {
    const saved = await team.save();
    if (saved.error && mounted.current) {
      append(note(`I applied it, but the mission could not be saved: ${saved.error}`, 'error'));
    }
  }

  const proposals: MissionProposals = {
    revision,
    activeId,
    request(instruction) {
      if (activeId !== null) close(outcomeOf(revision));
      const answer = pendingProposal();
      append(you(instruction), answer);
      setActiveId(answer.id);
      void revision.propose(instruction);
    },
    apply() {
      const { proposal } = revision;
      if (proposal === null) return;
      close({ state: 'applied', changes: proposal.changes });
      team.replace(proposal.pipeline);
      if (proposal.pipeline.id !== undefined) void saveApplied();
    },
    discard() {
      close({ state: 'discarded', changes: revision.proposal?.changes ?? [] });
    },
    settle() {
      if (activeId !== null) close(outcomeOf(revision));
    },
  };
  return proposals;
}
