import { X } from 'lucide-react';
import { useEffect, useId, useRef, type KeyboardEvent, type Ref } from 'react';

import type { AgentTool, PipelineInput, PipelineStep } from '../../core/api/types';
import { stepLabel } from '../pipelines/stages';
import { StepCard } from '../pipelines/StepEditor';

interface StepDrawerProps {
  step: PipelineStep;
  inputs: PipelineInput[];
  models: string[];
  tools: AgentTool[];
  /** A team keeps at least one agent. */
  canRemove: boolean;
  /** Why the models or tools could not be loaded, when they could not. */
  notice?: string;
  onChange: (patch: Partial<PipelineStep>) => void;
  onRemove: () => void;
  onClose: () => void;
  className?: string;
}

interface DrawerHeaderProps {
  title: string;
  headingId: string;
  headingRef: Ref<HTMLHeadingElement>;
  onClose: () => void;
}

/** The agent's name, which takes focus when the drawer opens, and the Close button. */
function DrawerHeader({ title, headingId, headingRef, onClose }: DrawerHeaderProps) {
  return (
    <div className="flex shrink-0 items-start gap-3 border-b border-white/[0.06] px-4 py-3 sm:px-5">
      <div className="min-w-0 flex-1">
        <p className="text-xs font-semibold tracking-widest text-sky-300 uppercase">Edit agent</p>
        <h2
          id={headingId}
          ref={headingRef}
          tabIndex={-1}
          className="mt-0.5 rounded text-lg font-semibold break-words text-white focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400"
        >
          {title}
        </h2>
      </div>
      <button
        type="button"
        onClick={onClose}
        className="inline-flex items-center gap-1.5 rounded-lg border border-white/15 px-2.5 py-1.5 text-sm font-medium text-slate-200 transition-colors hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400"
      >
        <X aria-hidden="true" className="size-4" />
        Close
      </button>
    </div>
  );
}

type DrawerBodyProps = Omit<StepDrawerProps, 'onClose' | 'className'>;

/** The scrolling part: a note on saving, and the builder's own editor for the agent. */
function DrawerBody({
  step,
  inputs,
  models,
  tools,
  canRemove,
  notice,
  onChange,
  onRemove,
}: DrawerBodyProps) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-5">
      <p className="mb-3 text-xs text-slate-400">
        Changes are saved for you a moment after you make them.
      </p>
      {notice && <p className="mb-3 text-xs text-amber-300">{notice}</p>}
      <StepCard
        key={step.order}
        step={step}
        inputs={inputs}
        availableModels={models}
        availableTools={tools}
        canRemove={canRemove}
        onChange={onChange}
        onRemove={onRemove}
      />
    </div>
  );
}

/**
 * Edits one agent beside the team: its role, task, tools, model and prompt, in the
 * builder's own step editor. A non-modal dialog: the team stays in view and another
 * agent can be picked meanwhile. Focus moves to its heading when it opens (or changes
 * agent); Escape and Close hand focus back (the hook above decides where).
 */
export function StepDrawer({ onClose, className = '', ...body }: StepDrawerProps) {
  const { step } = body;
  const headingId = useId();
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => heading.current?.focus(), [step.order]);

  function onKeyDown(event: KeyboardEvent) {
    if (event.key !== 'Escape') return;
    event.stopPropagation();
    onClose();
  }

  return (
    <aside
      role="dialog"
      aria-modal="false"
      aria-labelledby={headingId}
      onKeyDown={onKeyDown}
      className={`flex min-h-0 flex-col border-l border-white/10 bg-slate-950 shadow-[-24px_0_48px_-24px_rgba(0,0,0,0.8)] ${className}`}
    >
      <DrawerHeader
        title={step.role.trim() || stepLabel(step)}
        headingId={headingId}
        headingRef={heading}
        onClose={onClose}
      />
      <DrawerBody {...body} />
    </aside>
  );
}
