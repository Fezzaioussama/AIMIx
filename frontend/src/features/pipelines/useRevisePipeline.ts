import { useCallback, useState } from 'react';

import { ApiError } from '../../core/api/client';
import { revisePipeline } from '../../core/api/pipelines';
import type { Pipeline, PipelineChange, RevisedPipelineResponse } from '../../core/api/types';
import { useCancellableRequest } from '../../core/hooks/useCancellableRequest';
import { useLatest } from '../../core/hooks/useLatest';
import { adoptRevision } from './revision';

/** A proposed revision and the draft it was made from. */
export interface RevisionProposal {
  /** The draft the instruction was applied to. */
  basis: Pipeline;
  /** The whole revised pipeline; it keeps the draft's id, so saving it updates that pipeline. */
  pipeline: Pipeline;
  changes: PipelineChange[];
}

export interface RevisePipeline {
  /** The proposal for the current draft; null when there is none or the draft changed since. */
  proposal: RevisionProposal | null;
  /** A proposal was made for an earlier version of the draft and was set aside. */
  stale: boolean;
  /** A request is in flight. */
  busy: boolean;
  /** Why the last request failed; empty when it did not. */
  error: string;
  propose: (instruction: string, plannerModel?: string) => Promise<void>;
  /** Stops waiting for the request in flight. */
  cancel: () => void;
  /** Drops the proposal and any error. */
  discard: () => void;
}

const CHANGED_WHILE_WORKING =
  'The pipeline changed while AIMIx was working. Ask again to use the latest version.';

/** Plainer words for failures a person can act on; anything else keeps the server's message. */
const FRIENDLY_ERRORS: Record<string, string> = {
  upstream_response_invalid: 'AIMIx could not turn that into a change. Try saying it another way.',
};

function failureMessage(cause: unknown): string {
  if (cause instanceof ApiError) return FRIENDLY_ERRORS[cause.code] ?? cause.message;
  return cause instanceof Error ? cause.message : 'AIMIx could not propose changes.';
}

function toProposal(basis: Pipeline, response: RevisedPipelineResponse): RevisionProposal {
  const pipeline = adoptRevision(basis, response.revised_pipeline);
  return { basis, pipeline, changes: response.changes };
}

/** The proposal while it still applies to `pipeline`; past that it is stale. */
function forDraft(proposal: RevisionProposal | null, pipeline: Pipeline) {
  const current = proposal?.basis === pipeline ? proposal : null;
  return { proposal: current, stale: proposal !== null && current === null };
}

/**
 * Proposes a revision of `pipeline` from one instruction (POST /api/pipelines/revise).
 * Nothing is saved or applied here; the caller decides what to do with the proposal.
 * A proposal belongs to the draft it was made from, so editing the draft sets it aside,
 * and leaving the screen cancels a request in flight.
 */
export function useRevisePipeline(pipeline: Pipeline): RevisePipeline {
  const [proposal, setProposal] = useState<RevisionProposal | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const latest = useLatest(pipeline);
  const { start, cancel, finish } = useCancellableRequest();

  const propose = useCallback(
    async (instruction: string, plannerModel?: string) => {
      if (!instruction.trim()) {
        setError('Describe the change you want first.');
        return;
      }
      const controller = start();
      const basis = latest.current;
      setBusy(true);
      setError('');
      setProposal(null);
      try {
        const response = await revisePipeline(
          basis,
          instruction.trim(),
          plannerModel,
          controller.signal,
        );
        if (controller.signal.aborted) return;
        if (latest.current === basis) setProposal(toProposal(basis, response));
        else setError(CHANGED_WHILE_WORKING);
      } catch (cause) {
        if (!controller.signal.aborted) setError(failureMessage(cause));
      } finally {
        if (finish(controller)) setBusy(false);
      }
    },
    [finish, latest, start],
  );

  const discard = useCallback(() => {
    setProposal(null);
    setError('');
  }, []);

  return { ...forDraft(proposal, pipeline), busy, error, propose, cancel, discard };
}
