import { StarBorder } from '../../core/ui/reactbits/StarBorder';
import type { GraphNode, NodeStatus } from './pipelineGraph';
import { modelLabel } from './modelLabel';
import { roundLabel } from './roundNotes';
import { stepLabel } from './stages';
import { describeReview } from './stepFlow';

// Fixed height: the fork/merge brackets in PipelineGraph meet node centres.
const nodeBase =
  'relative flex h-[88px] flex-col justify-between rounded-xl border bg-slate-900 p-3 text-left transition-[transform,background-color,box-shadow] duration-300 enabled:hover:-translate-y-0.5';

/** Each step status's look and words, shared by the diagram and the step progress cards. */
export const NODE_STATUS_STYLES: Record<
  NodeStatus,
  { border: string; dot: string; label: string; text: string }
> = {
  pending: {
    border: 'border-white/10',
    dot: 'bg-slate-500',
    label: 'Not run',
    text: 'text-slate-400',
  },
  waiting: {
    border: 'border-white/10',
    dot: 'bg-slate-400',
    label: 'Waiting',
    text: 'text-slate-300',
  },
  running: {
    border: 'border-sky-400/30 shadow-[0_0_30px_-10px_rgba(56,189,248,0.7)]',
    dot: 'bg-sky-400',
    label: 'Running',
    text: 'text-sky-300',
  },
  done: {
    border: 'border-emerald-400/40 shadow-[0_0_24px_-12px_rgba(52,211,153,0.7)]',
    dot: 'bg-emerald-400',
    label: 'Done',
    text: 'text-emerald-300',
  },
  failed: {
    border: 'border-red-400/50 shadow-[0_0_24px_-12px_rgba(248,113,113,0.7)]',
    dot: 'bg-red-400',
    label: 'Failed',
    text: 'text-red-300',
  },
  stopped: {
    border: 'border-amber-400/40',
    dot: 'bg-amber-400',
    label: 'Stopped',
    text: 'text-amber-300',
  },
  // Muted and dashed: it did not run, and nothing is wrong.
  skipped: {
    border: 'border-dashed border-white/15',
    dot: 'bg-slate-600 ring-1 ring-slate-400',
    label: 'Skipped',
    text: 'text-slate-400',
  },
};

/** Why a skipped step did not run, in the words shown on hover and in the step list. */
export const SKIPPED_REASON = 'Its condition was not met';

interface GraphNodeCardProps {
  node: GraphNode;
  selected: boolean;
  /** The step's condition in words ("the previous result contains “blog”"); null without one. */
  conditionText?: string | null;
  onClick?: () => void;
}

/** What a screen reader hears of a node: the step, its status and what makes it special. */
function describeNode(node: GraphNode, label: string, conditionText: string | null): string {
  const parts = [
    stepLabel(node),
    modelLabel(node.model),
    node.isOutput ? 'output' : 'intermediate',
    label,
  ];
  if (node.status === 'skipped') parts.push(SKIPPED_REASON.toLowerCase());
  if (conditionText) parts.push(`runs only if ${conditionText}`);
  if (node.review) parts.push(describeReview(node.review).toLowerCase());
  if (node.round > 1) parts.push(roundLabel(node.round, node.roundTotal).toLowerCase());
  return parts.join(', ');
}

/** The hover text: why it was skipped, else what it runs on; its condition comes first. */
function hoverText(node: GraphNode, conditionText: string | null): string {
  if (node.status === 'skipped') {
    return conditionText ? `${SKIPPED_REASON}: it runs only if ${conditionText}` : SKIPPED_REASON;
  }
  return conditionText ? `Runs only if ${conditionText}\n\n${node.prompt}` : node.prompt;
}

export function GraphNodeCard({
  node,
  selected,
  conditionText = null,
  onClick,
}: GraphNodeCardProps) {
  const style = NODE_STATUS_STYLES[node.status];
  const running = node.status === 'running';
  const summary =
    node.outputLength === null
      ? node.expectedOutput.trim() || node.prompt || 'No prompt yet'
      : `${node.outputLength} chars`;

  return (
    <button
      type="button"
      disabled={!onClick}
      onClick={onClick}
      title={hoverText(node, conditionText)}
      aria-label={describeNode(node, style.label, conditionText)}
      className={`${nodeBase} w-56 ${style.border} ${node.isOutput ? 'bg-amber-400/5' : ''} ${
        selected ? 'ring-2 ring-sky-400' : ''
      } enabled:cursor-pointer enabled:hover:bg-slate-800 disabled:cursor-default`}
    >
      {running && <StarBorder speed={2.2} />}
      <span className="flex items-center gap-2 text-xs">
        <span className="rounded bg-sky-400/15 px-1.5 py-0.5 font-semibold text-sky-400">
          #{node.order}
        </span>
        <span className="flex-1 truncate font-semibold text-slate-100">{stepLabel(node)}</span>
        <span className="relative flex size-2 shrink-0" title={style.label}>
          {running && (
            <span className="absolute inset-0 rounded-full bg-sky-400 opacity-70 motion-safe:animate-ping" />
          )}
          <span className={`relative size-2 rounded-full ${style.dot}`} />
        </span>
      </span>
      <span className="flex min-w-0 items-center gap-1.5 text-[11px] text-slate-400">
        <span className="min-w-0 truncate">{modelLabel(node.model)}</span>
        {node.isOutput && <OutputBadge />}
        <FlowMarks node={node} />
      </span>
      <span className="truncate text-[11px] text-slate-400">{summary}</span>
    </button>
  );
}

const MARK =
  'shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold tracking-wide whitespace-nowrap';

/** Marks a step that runs only while its condition holds. */
export function ConditionBadge() {
  return <span className={`${MARK} bg-indigo-400/15 text-indigo-200`}>Only if…</span>;
}

/** Marks a step that reviews the work and can send it back. */
export function ReviewBadge() {
  return <span className={`${MARK} bg-purple-400/15 text-purple-200`}>Reviewer</span>;
}

/** Small marks for what sets a step apart: a condition, a review loop, a later round. */
function FlowMarks({ node }: { node: GraphNode }) {
  return (
    <>
      {node.condition !== null && <ConditionBadge />}
      {node.review !== null && <ReviewBadge />}
      {node.round > 1 && (
        <span className={`${MARK} bg-sky-400/15 text-sky-200`}>
          {roundLabel(node.round, node.roundTotal)}
        </span>
      )}
    </>
  );
}

/** Marks a step whose result is one of the pipeline's outputs. */
export function OutputBadge() {
  return (
    <span className="shrink-0 rounded bg-amber-400/15 px-1.5 py-0.5 text-[10px] font-semibold tracking-wide text-amber-300 uppercase">
      Output
    </span>
  );
}

interface GraphTerminalProps {
  label: string;
  detail: string;
  active?: boolean;
  onClick?: () => void;
}

/** The Input and Output ends of the diagram. */
export function GraphTerminal({ label, detail, active = false, onClick }: GraphTerminalProps) {
  return (
    <button
      type="button"
      disabled={!onClick}
      onClick={onClick}
      className={`${nodeBase} w-36 border-indigo-400/40 bg-gradient-to-br from-indigo-500/20 to-purple-500/10 ${
        active ? 'ring-2 ring-sky-400' : ''
      } enabled:cursor-pointer enabled:hover:bg-indigo-500/20 disabled:cursor-default`}
    >
      <span className="text-xs font-semibold tracking-wide text-indigo-300 uppercase">{label}</span>
      <span className="line-clamp-2 text-xs text-slate-400">{detail}</span>
    </button>
  );
}
