import type { PipelineStep, StepResult } from '../../core/api/types';
import { GraphNodeCard, GraphTerminal } from './GraphNodeCard';
import { buildGraph, type GraphNode, type OutputTarget } from './pipelineGraph';

interface PipelineGraphProps {
  steps: PipelineStep[];
  results?: StepResult[];
  isRunning?: boolean;
  input?: string;
  hasFinalOutput?: boolean;
  selected?: OutputTarget | null;
  onSelect?: (target: OutputTarget) => void;
}

/**
 * Left-to-right flow diagram: Input → stages → Output. Parallel steps of a
 * stage are stacked and joined by fork/merge brackets.
 */
export function PipelineGraph({
  steps,
  results = [],
  isRunning = false,
  input = '',
  hasFinalOutput = false,
  selected = null,
  onSelect,
}: PipelineGraphProps) {
  const stages = buildGraph(steps, results, isRunning);

  return (
    <div className="overflow-x-auto rounded-2xl border border-white/10 bg-slate-950/40 p-6">
      <div className="flex min-w-max items-center pt-6" role="list" aria-label="Pipeline diagram">
        <GraphTerminal label="Input" detail={input || 'Your text'} />
        {stages.map((stage) => (
          <div key={stage.stage} className="flex items-center" role="listitem">
            <Connector />
            <StageColumn
              stage={stage.stage}
              nodes={stage.items}
              selected={selected}
              onSelect={onSelect}
            />
          </div>
        ))}
        <Connector />
        <GraphTerminal
          label="Output"
          detail={hasFinalOutput ? 'View final output' : 'Final result'}
          active={selected === 'final'}
          onClick={hasFinalOutput && onSelect ? () => onSelect('final') : undefined}
        />
      </div>
    </div>
  );
}

interface StageColumnProps {
  stage: number;
  nodes: GraphNode[];
  selected: OutputTarget | null;
  onSelect?: (target: OutputTarget) => void;
}

function StageColumn({ stage, nodes, selected, onSelect }: StageColumnProps) {
  const parallel = nodes.length > 1;
  return (
    <div className={`relative flex flex-col gap-3 ${parallel ? 'px-3' : ''}`}>
      <span className="absolute -top-6 right-0 left-0 text-center text-[10px] font-semibold tracking-wide text-slate-500 uppercase">
        Stage {stage}
        {parallel ? ' · parallel' : ''}
      </span>
      {parallel && (
        <>
          {/* Fork on the left, merge on the right; both span node centre to centre. */}
          <span className="absolute top-11 bottom-11 left-0 w-3 rounded-l-md border-y border-l border-slate-500" />
          <span className="absolute top-11 right-0 bottom-11 w-3 rounded-r-md border-y border-r border-slate-500" />
        </>
      )}
      {nodes.map((node) => (
        <GraphNodeCard
          key={node.order}
          node={node}
          selected={selected === node.order}
          onClick={node.status === 'done' && onSelect ? () => onSelect(node.order) : undefined}
        />
      ))}
    </div>
  );
}

function Connector() {
  return (
    <div className="flex w-10 items-center" aria-hidden="true">
      <span className="h-px flex-1 bg-slate-500" />
      <span className="border-y-4 border-l-[6px] border-y-transparent border-l-slate-500" />
    </div>
  );
}
