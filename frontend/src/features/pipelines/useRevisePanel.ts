import { useRef, useState } from 'react';

import type { Pipeline } from '../../core/api/types';
import { useRevisePipeline } from './useRevisePipeline';

/**
 * The revise panel's own state over `useRevisePipeline`: the typed instruction, whether
 * the last proposal was applied, and the actions on them. Applying hands the revision to
 * `onApply` and never saves.
 */
export function useRevisePanel(
  pipeline: Pipeline,
  onApply: (revised: Pipeline) => void,
  plannerModel?: string,
) {
  const [instruction, setInstruction] = useState('');
  const [applied, setApplied] = useState(false);
  const field = useRef<HTMLTextAreaElement>(null);
  const revision = useRevisePipeline(pipeline);

  function edit(value: string) {
    setInstruction(value);
    setApplied(false);
    if (revision.stale) revision.discard();
  }

  return {
    revision,
    instruction,
    applied,
    field,
    edit,
    pick(example: string) {
      edit(example);
      field.current?.focus();
    },
    ask() {
      setApplied(false);
      void revision.propose(instruction, plannerModel);
    },
    apply() {
      if (revision.proposal) onApply(revision.proposal.pipeline);
      revision.discard();
      setInstruction('');
      setApplied(true);
      field.current?.focus();
    },
    discard() {
      revision.discard();
      field.current?.focus();
    },
  };
}

export type RevisePanelState = ReturnType<typeof useRevisePanel>;

export type PanelTone = 'idle' | 'busy' | 'ready' | 'stale' | 'applied';

/** What the panel's status line says, and in which tone. */
export function panelStatus({ revision, applied }: RevisePanelState): {
  tone: PanelTone;
  text: string;
} {
  if (revision.busy) return { tone: 'busy', text: 'AIMIx is working on your change…' };
  if (revision.proposal) {
    const count = revision.proposal.changes.length;
    const text = `Proposal ready: ${count} ${count === 1 ? 'change' : 'changes'} to review.`;
    return { tone: 'ready', text };
  }
  if (revision.stale) {
    const text = 'The pipeline changed after you asked, so that proposal was set aside. Ask again.';
    return { tone: 'stale', text };
  }
  if (applied) return { tone: 'applied', text: 'Changes applied. Save the pipeline to keep them.' };
  return { tone: 'idle', text: '' };
}
