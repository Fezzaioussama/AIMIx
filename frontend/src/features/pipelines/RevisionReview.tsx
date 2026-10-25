import { Minus, PencilLine, Plus, type LucideIcon } from 'lucide-react';
import { useId } from 'react';

import type { PipelineChange } from '../../core/api/types';
import { AnimatedContent } from '../../core/ui/reactbits/AnimatedContent';
import { PRIMARY_BUTTON, SECONDARY_BUTTON } from './buttonStyles';
import { PipelineGraph } from './PipelineGraph';
import { describeChange } from './revision';
import type { RevisionProposal } from './useRevisePipeline';

const KIND_MARKS: Record<PipelineChange['kind'], { icon: LucideIcon; className: string }> = {
  added: { icon: Plus, className: 'text-emerald-300' },
  changed: { icon: PencilLine, className: 'text-sky-300' },
  removed: { icon: Minus, className: 'text-rose-300' },
};

interface RevisionReviewProps {
  proposal: RevisionProposal;
  onApply: () => void;
  onDiscard: () => void;
  /** The page is busy (saving, running), so the draft must not be replaced now. */
  applyDisabled?: boolean;
  headingLevel?: 3 | 4;
}

/** A proposed revision: what it changes, a preview of the result, and Apply or Discard. */
export function RevisionReview({
  proposal,
  onApply,
  onDiscard,
  applyDisabled = false,
  headingLevel = 3,
}: RevisionReviewProps) {
  const headingId = useId();
  const Heading = headingLevel === 3 ? 'h3' : 'h4';
  const { changes, pipeline } = proposal;
  const hasChanges = changes.length > 0;

  return (
    <AnimatedContent distance={16} className="mt-5">
      <section
        aria-labelledby={headingId}
        className="min-w-0 rounded-xl border border-white/10 bg-slate-950/60 p-4 sm:p-5"
      >
        <Heading id={headingId} className="mb-3 text-sm font-semibold text-slate-100">
          {hasChanges ? `Proposed changes (${changes.length})` : 'Nothing to change'}
        </Heading>
        {hasChanges ? (
          <>
            <ChangeList changes={changes} />
            <p className="mt-5 mb-2 text-xs font-semibold tracking-wide text-slate-400 uppercase">
              Preview
            </p>
            <PipelineGraph steps={pipeline.steps} inputs={pipeline.inputs} />
          </>
        ) : (
          <p className="text-sm text-slate-300">
            AIMIx left the pipeline as it is. Try describing the change another way.
          </p>
        )}
        <ReviewActions
          hasChanges={hasChanges}
          applyDisabled={applyDisabled}
          onApply={onApply}
          onDiscard={onDiscard}
        />
      </section>
    </AnimatedContent>
  );
}

type ReviewActionsProps = Required<
  Pick<RevisionReviewProps, 'applyDisabled' | 'onApply' | 'onDiscard'>
> & { hasChanges: boolean };

/** Apply and Discard; with nothing to apply, only Close. */
function ReviewActions({ hasChanges, applyDisabled, onApply, onDiscard }: ReviewActionsProps) {
  return (
    <div className="mt-4 flex flex-wrap items-center gap-3">
      {hasChanges && (
        <button type="button" onClick={onApply} disabled={applyDisabled} className={PRIMARY_BUTTON}>
          Apply changes
        </button>
      )}
      <button type="button" onClick={onDiscard} className={SECONDARY_BUTTON}>
        {hasChanges ? 'Discard' : 'Close'}
      </button>
      {hasChanges && (
        <p className="text-xs text-slate-400">
          Applying replaces your draft. Nothing is saved until you save.
        </p>
      )}
    </div>
  );
}

/** The changes in plain words, each marked added, changed or removed. */
export function ChangeList({ changes }: { changes: PipelineChange[] }) {
  return (
    <ul className="space-y-2">
      {changes.map((change, index) => {
        const { icon: Icon, className } = KIND_MARKS[change.kind];
        return (
          <li
            key={`${change.target}-${change.kind}-${change.label}-${index}`}
            className="flex items-start gap-2 text-sm text-slate-200"
          >
            <Icon aria-hidden="true" className={`mt-0.5 size-4 shrink-0 ${className}`} />
            <span className="min-w-0 break-words">{describeChange(change)}</span>
          </li>
        );
      })}
    </ul>
  );
}
