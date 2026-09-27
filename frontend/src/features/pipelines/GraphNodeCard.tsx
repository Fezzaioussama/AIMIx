import type { GraphNode, NodeStatus } from './pipelineGraph';
import { modelLabel } from './modelLabel';
import { stepLabel } from './stages';

// Fixed height: the fork/merge brackets in PipelineGraph meet node centres.
const nodeBase =
  'flex h-[88px] flex-col justify-between rounded-xl border bg-slate-900 p-3 text-left transition-colors';

const statusStyles: Record<NodeStatus, { border: string; dot: string; label: string }> = {
  pending: { border: 'border-white/10', dot: 'bg-slate-500', label: 'Not run' },
  running: { border: 'border-sky-400/60 animate-pulse', dot: 'bg-sky-400', label: 'Running' },
  done: { border: 'border-emerald-400/40', dot: 'bg-emerald-400', label: 'Done' },
};

interface GraphNodeCardProps {
  node: GraphNode;
  selected: boolean;
  onClick?: () => void;
}

export function GraphNodeCard({ node, selected, onClick }: GraphNodeCardProps) {
  const style = statusStyles[node.status];
  const summary =
    node.outputLength === null ? node.prompt || 'No prompt yet' : `${node.outputLength} chars`;

  return (
    <button
      type="button"
      disabled={!onClick}
      onClick={onClick}
      title={node.prompt}
      aria-label={`${stepLabel(node)}, ${modelLabel(node.model)}, ${
        node.isOutput ? 'output' : 'intermediate'
      }, ${style.label}`}
      className={`${nodeBase} w-56 ${style.border} ${node.isOutput ? 'bg-amber-400/5' : ''} ${
        selected ? 'ring-2 ring-sky-400' : ''
      } enabled:cursor-pointer enabled:hover:bg-slate-800 disabled:cursor-default`}
    >
      <span className="flex items-center gap-2 text-xs">
        <span className="rounded bg-sky-400/15 px-1.5 py-0.5 font-semibold text-sky-400">
          #{node.order}
        </span>
        <span className="flex-1 truncate font-semibold text-slate-100">{stepLabel(node)}</span>
        <span className={`size-2 shrink-0 rounded-full ${style.dot}`} title={style.label} />
      </span>
      <span className="flex items-center gap-2 text-[11px] text-slate-400">
        <span className="truncate">{modelLabel(node.model)}</span>
        {node.isOutput && <OutputBadge />}
      </span>
      <span className="truncate text-[11px] text-slate-500">{summary}</span>
    </button>
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
      className={`${nodeBase} w-36 border-indigo-400/40 bg-indigo-500/10 ${
        active ? 'ring-2 ring-sky-400' : ''
      } enabled:cursor-pointer enabled:hover:bg-indigo-500/20 disabled:cursor-default`}
    >
      <span className="text-xs font-semibold tracking-wide text-indigo-300 uppercase">{label}</span>
      <span className="line-clamp-2 text-xs text-slate-400">{detail}</span>
    </button>
  );
}
