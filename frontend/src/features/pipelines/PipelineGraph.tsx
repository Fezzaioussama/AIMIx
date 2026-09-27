import type { PipelineStep, StepResult } from '../../core/api/types';
import { GraphNodeCard, GraphTerminal, OutputBadge } from './GraphNodeCard';
import { buildGraph, type GraphNode, type OutputTarget } from './pipelineGraph';

interface PipelineGraphProps {
  steps: PipelineStep[];
  results?: StepResult[];
  isRunning?: boolean;
  input?: string;
  selected?: OutputTarget | null;
  onSelect?: (target: OutputTarget) => void;
  onEditStep?: (order: number) => void;
  onAddParallel?: (stage: number) => void;
  onAddAfter?: (stage: number) => void;
  parallelLabel?: string;
  nextLabel?: string;
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
  selected = null,
  onSelect,
  onEditStep,
  onAddParallel,
  onAddAfter,
  parallelLabel = '+ Parallel step',
  nextLabel = '+ Next stage',
}: PipelineGraphProps) {
  const stages = buildGraph(steps, results, isRunning);
  const outputCount = stages.flatMap((stage) => stage.items).filter((node) => node.isOutput).length;
  const hasRun = results.length > 0;

  return (
    <div className="overflow-x-auto rounded-2xl border border-white/10 bg-slate-950/40 p-6">
      <p className="mb-8 text-xs text-slate-400">
        Each stage receives the previous stage’s result. Steps in one stage share its input and
        run in parallel. Mark steps as Output to keep their results.
        {onEditStep && ' Select a step to edit its prompt.'}
      </p>
      <div className="flex min-w-max items-start pt-6" role="list" aria-label="Pipeline diagram">
        <GraphTerminal label="Input" detail={input || 'Your text'} />
        {stages.map((stage) => (
          <div key={stage.stage} className="flex items-start" role="listitem">
            <Connector />
            <StageColumn
              stage={stage.stage}
              nodes={stage.items}
              selected={selected}
              onSelect={onSelect}
              onEditStep={onEditStep}
              onAddParallel={onAddParallel}
              onAddAfter={onAddAfter}
              parallelLabel={parallelLabel}
              nextLabel={nextLabel}
            />
          </div>
        ))}
        <Connector />
        <GraphTerminal
          label={outputCount === 1 ? 'Output' : 'Outputs'}
          detail={`${outputCount} ${outputCount === 1 ? 'result' : 'results'}${hasRun ? ' · view' : ''}`}
          active={selected === 'outputs'}
          onClick={hasRun && onSelect ? () => onSelect('outputs') : undefined}
        />
      </div>
      <Legend />
    </div>
  );
}

interface StageColumnProps {
  stage: number;
  nodes: GraphNode[];
  selected: OutputTarget | null;
  onSelect?: (target: OutputTarget) => void;
  onEditStep?: (order: number) => void;
  onAddParallel?: (stage: number) => void;
  onAddAfter?: (stage: number) => void;
  parallelLabel: string;
  nextLabel: string;
}

function StageColumn({
  stage,
  nodes,
  selected,
  onSelect,
  onEditStep,
  onAddParallel,
  onAddAfter,
  parallelLabel,
  nextLabel,
}: StageColumnProps) {
  return (
    <div className="flex flex-col gap-3">
      <StageNodes {...{ stage, nodes, selected, onSelect, onEditStep }} />
      <StageActions {...{ stage, onAddParallel, onAddAfter, parallelLabel, nextLabel }} />
    </div>
  );
}

type StageNodesProps = Pick<
  StageColumnProps,
  'stage' | 'nodes' | 'selected' | 'onSelect' | 'onEditStep'
>;

function StageNodes({ stage, nodes, selected, onSelect, onEditStep }: StageNodesProps) {
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
          onClick={
            node.status === 'done' && onSelect
              ? () => onSelect(node.order)
              : onEditStep ? () => onEditStep(node.order) : undefined
          }
        />
      ))}
    </div>
  );
}

type StageActionsProps = Pick<
  StageColumnProps,
  'stage' | 'onAddParallel' | 'onAddAfter' | 'parallelLabel' | 'nextLabel'
>;

function StageActions({
  stage, onAddParallel, onAddAfter, parallelLabel, nextLabel,
}: StageActionsProps) {
  if (!onAddParallel && !onAddAfter) return null;
  return (
    <div className="flex gap-2 text-[11px]">
      {onAddParallel && (
        <button type="button" onClick={() => onAddParallel(stage)} className="rounded-md border border-dashed border-sky-400/40 px-2 py-1 text-sky-300 hover:bg-sky-400/10">
          {parallelLabel}
        </button>
      )}
      {onAddAfter && (
        <button type="button" onClick={() => onAddAfter(stage)} className="rounded-md border border-dashed border-white/20 px-2 py-1 text-slate-300 hover:bg-white/10">
          {nextLabel}
        </button>
      )}
    </div>
  );
}

function Legend() {
  return (
    <div className="mt-4 flex flex-wrap items-center gap-4 text-[11px] text-slate-500">
      <span className="flex items-center gap-1.5">
        <OutputBadge /> result you receive
      </span>
      <span>If no output is marked, the last stage becomes the output.</span>
      <span>Stacked steps run in parallel.</span>
    </div>
  );
}

function Connector() {
  return (
    <div className="mt-11 flex w-10 items-center" aria-hidden="true">
      <span className="h-px flex-1 bg-slate-500" />
      <span className="border-y-4 border-l-[6px] border-y-transparent border-l-slate-500" />
    </div>
  );
}
