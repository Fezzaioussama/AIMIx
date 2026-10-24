import { ChevronDown, Sparkles } from 'lucide-react';
import { useId, useState, type ReactNode, type SyntheticEvent } from 'react';

import type { Pipeline } from '../../core/api/types';
import { Spinner } from '../../core/ui/Spinner';
import { ShinyText } from '../../core/ui/reactbits/ShinyText';
import { PRIMARY_BUTTON, SECONDARY_BUTTON } from './buttonStyles';
import { RevisionReview } from './RevisionReview';
import { REVISION_EXAMPLES, REVISION_INSTRUCTION_MAX_LENGTH } from './revision';
import {
  panelStatus,
  useRevisePanel,
  type PanelTone,
  type RevisePanelState,
} from './useRevisePanel';

export interface RevisePanelProps {
  /** The draft to change; it may be unsaved. */
  pipeline: Pipeline;
  /**
   * Receives the revised draft when the user applies it. The caller replaces its draft and
   * treats it as unsaved: nothing is ever saved from this panel.
   */
  onApply: (revised: Pipeline) => void;
  /** The model that plans the change; omitted means the account's default model. */
  plannerModel?: string;
  /** The page is busy (saving, running): no new request, and nothing is applied. */
  disabled?: boolean;
  /** Start expanded instead of as a single bar. */
  defaultOpen?: boolean;
  /** The panel title's heading level; the review's heading goes one deeper. */
  headingLevel?: 2 | 3;
  className?: string;
}

/**
 * "Ask AIMIx to change this pipeline": one sentence in, a proposed revision out, shown as
 * a change list and a preview. Apply hands the revision to `onApply`; Discard drops it.
 */
export function RevisePanel({
  pipeline,
  onApply,
  plannerModel,
  disabled = false,
  defaultOpen = false,
  headingLevel = 2,
  className = '',
}: RevisePanelProps) {
  const id = useId();
  const [open, setOpen] = useState(defaultOpen);
  const panel = useRevisePanel(pipeline, onApply, plannerModel);
  const { revision } = panel;

  return (
    <section
      aria-labelledby={`${id}-title`}
      className={`rounded-2xl border border-indigo-400/20 bg-[linear-gradient(135deg,rgba(99,102,241,0.10),rgba(168,85,247,0.05))] ${className}`}
    >
      <PanelToggle id={id} level={headingLevel} open={open} onToggle={() => setOpen(!open)} />
      <Foldable id={`${id}-body`} open={open}>
        <InstructionForm id={id} panel={panel} disabled={disabled} />
        <StatusLine panel={panel} />
        {revision.error && (
          <p role="alert" className="mt-3 rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-300">
            {revision.error}
          </p>
        )}
        {revision.proposal && (
          <RevisionReview
            proposal={revision.proposal}
            headingLevel={headingLevel === 2 ? 3 : 4}
            applyDisabled={disabled}
            onApply={panel.apply}
            onDiscard={panel.discard}
          />
        )}
      </Foldable>
    </section>
  );
}

interface PanelToggleProps {
  id: string;
  level: 2 | 3;
  open: boolean;
  onToggle: () => void;
}

function PanelToggle({ id, level, open, onToggle }: PanelToggleProps) {
  const Heading = level === 2 ? 'h2' : 'h3';
  return (
    <Heading id={`${id}-title`}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={`${id}-body`}
        onClick={onToggle}
        className="flex w-full cursor-pointer items-center gap-3 rounded-2xl px-4 py-3.5 text-left text-sm font-semibold text-slate-100 transition-colors hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 sm:px-5"
      >
        <Sparkles aria-hidden="true" className="size-4 shrink-0 text-indigo-300" />
        <span className="flex-1">Ask AIMIx to change this pipeline</span>
        <ChevronDown
          aria-hidden="true"
          className={`size-4 shrink-0 text-slate-400 transition-transform duration-300 motion-reduce:transition-none ${open ? 'rotate-180' : ''}`}
        />
      </button>
    </Heading>
  );
}

/** Opens by animating its grid row; `inert` keeps folded content out of reach. */
function Foldable({ id, open, children }: { id: string; open: boolean; children: ReactNode }) {
  return (
    <div
      id={id}
      inert={!open}
      className={`grid transition-[grid-template-rows] duration-300 motion-reduce:transition-none ${open ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}
    >
      <div className="min-w-0 overflow-hidden">
        <div className="px-4 pb-5 sm:px-5">{children}</div>
      </div>
    </div>
  );
}

const FIELD_CLASS =
  'w-full resize-y rounded-xl border border-white/10 bg-slate-950/60 p-3 text-sm text-slate-100 transition-[border-color,box-shadow] outline-none placeholder:text-slate-400 focus:border-sky-400/60 focus:shadow-[0_0_0_3px_rgba(56,189,248,0.12)] disabled:opacity-60';

/** The change box, example instructions, and the button that asks (Ctrl/⌘ + Enter too). */
function InstructionForm({
  id,
  panel,
  disabled,
}: {
  id: string;
  panel: RevisePanelState;
  disabled: boolean;
}) {
  const { busy, cancel } = panel.revision;
  const ready = !busy && !disabled && panel.instruction.trim() !== '';

  function submit(event: SyntheticEvent) {
    event.preventDefault();
    if (ready) panel.ask();
  }

  return (
    <form onSubmit={submit}>
      <label
        htmlFor={`${id}-instruction`}
        className="mb-1 block text-sm font-medium text-slate-200"
      >
        What should change?
      </label>
      <p id={`${id}-hint`} className="mb-2 text-xs text-slate-400">
        Say it in a sentence. You review the changes before anything is replaced.
      </p>
      <textarea
        id={`${id}-instruction`}
        ref={panel.field}
        rows={2}
        value={panel.instruction}
        maxLength={REVISION_INSTRUCTION_MAX_LENGTH}
        disabled={busy}
        aria-describedby={`${id}-hint`}
        placeholder="e.g. Add an SEO agent that works alongside the marketing agent"
        onChange={(event) => panel.edit(event.target.value)}
        onKeyDown={(event) =>
          event.key === 'Enter' && (event.ctrlKey || event.metaKey) && submit(event)
        }
        className={FIELD_CLASS}
      />
      <ExampleInstructions disabled={busy} onPick={panel.pick} />
      <AskButtons busy={busy} ready={ready} onCancel={cancel} />
    </form>
  );
}

function AskButtons({
  busy,
  ready,
  onCancel,
}: {
  busy: boolean;
  ready: boolean;
  onCancel: () => void;
}) {
  return (
    <div className="mt-4 flex flex-wrap items-center gap-3">
      <button type="submit" disabled={!ready} className={PRIMARY_BUTTON}>
        {busy && <Spinner decorative className="size-4" />}
        {busy ? 'Working on it…' : 'Propose changes'}
      </button>
      {busy && (
        <button type="button" onClick={onCancel} className={SECONDARY_BUTTON}>
          Stop
        </button>
      )}
    </div>
  );
}

function ExampleInstructions({
  disabled,
  onPick,
}: {
  disabled: boolean;
  onPick: (example: string) => void;
}) {
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
      <span className="text-slate-400">Try:</span>
      {REVISION_EXAMPLES.map((example) => (
        <button
          key={example}
          type="button"
          disabled={disabled}
          onClick={() => onPick(example)}
          className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-left text-slate-200 transition-colors hover:border-indigo-300/40 hover:bg-indigo-400/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {example}
        </button>
      ))}
    </div>
  );
}

/** Busy, stale and applied notes are shown; the rest is announced to screen readers only. */
const TONE_CLASS: Record<PanelTone, string> = {
  idle: 'sr-only',
  ready: 'sr-only',
  busy: 'mt-3 text-sm text-slate-300',
  stale: 'mt-3 text-sm text-amber-300',
  applied: 'mt-3 text-sm text-emerald-300',
};

/** One polite live region, always present, so every status change is announced. */
function StatusLine({ panel }: { panel: RevisePanelState }) {
  const { tone, text } = panelStatus(panel);
  return (
    <p role="status" className={TONE_CLASS[tone]}>
      {tone === 'busy' ? <ShinyText className="text-slate-300/90">{text}</ShinyText> : text}
    </p>
  );
}
