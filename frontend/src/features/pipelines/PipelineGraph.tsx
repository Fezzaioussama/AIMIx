import { motion } from 'motion/react';

import type { PipelineInput, PipelineStep, RunStep, StepResult } from '../../core/api/types';
import {
  ConditionBadge,
  GraphNodeCard,
  GraphTerminal,
  OutputBadge,
  ReviewBadge,
} from './GraphNodeCard';
import { CONNECTOR_WIDTH, columnWidth } from './graphLayout';
import { LoopRail } from './LoopRail';
import { buildGraph, type GraphNode, type OutputTarget } from './pipelineGraph';
import { inputsSummary } from './pipelineInputs';
import { describeCondition, reviewLoops } from './stepFlow';

/** A node the diagram can open: its output, or the error it stopped on. */
const SELECTABLE = new Set<GraphNode['status']>(['done', 'failed']);

interface PipelineGraphProps {
  steps: PipelineStep[];
  /** Named run inputs, listed on the Input terminal instead of the typed text. */
  inputs?: PipelineInput[];
  results?: StepResult[];
  /** The followed run's steps: each node shows its own live status. */
  liveSteps?: RunStep[];
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

/** Stages slide in left to right, one after another, as the diagram appears. */
function stageEntrance(stage: number) {
  return {
    initial: { opacity: 0, x: -14 },
    animate: { opacity: 1, x: 0 },
    transition: {
      duration: 0.45,
      delay: Math.min(Math.max(stage - 1, 0), 8) * 0.07,
      ease: [0.16, 1, 0.3, 1] as const,
    },
  };
}

/**
 * Left-to-right flow diagram: Input → stages → Output. Parallel steps of a
 * stage are stacked and joined by fork/merge brackets.
 */
export function PipelineGraph({
  steps,
  inputs = [],
  results = [],
  liveSteps,
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
  const stages = buildGraph(steps, results, isRunning, liveSteps);
  const nodes = stages.flatMap((stage) => stage.items);
  const outputCount = nodes.filter((node) => node.isOutput).length;
  const hasRun = results.length > 0;
  const loops = reviewLoops(steps);
  const conditionTextOf = (order: number) => {
    const step = steps.find((candidate) => candidate.order === order);
    return step ? describeCondition(step, steps, inputs) : null;
  };

  return (
    <div className="overflow-x-auto rounded-2xl border border-white/10 bg-slate-950/50 bg-[radial-gradient(rgba(148,163,184,0.09)_1px,transparent_1px)] bg-[size:18px_18px] p-6">
      <p className="mb-8 text-xs text-slate-400">
        Each stage receives the previous stage’s result. Steps in one stage share its input and run
        in parallel. Mark steps as Output to keep their results.
        {onEditStep && ' Select a step to edit its prompt.'}
      </p>
      {loops.length > 0 && <LoopRail stages={stages} loops={loops} />}
      <div className="flex min-w-max items-start pt-6" role="list" aria-label="Pipeline diagram">
        <GraphTerminal
          label={inputs.length > 1 ? 'Inputs' : 'Input'}
          detail={inputsSummary(inputs, input)}
        />
        {stages.map((stage) => (
          <div key={stage.stage} className="flex items-start" role="listitem">
            <Connector flowing={isRunning} />
            <StageColumn
              stage={stage.stage}
              nodes={stage.items}
              selected={selected}
              conditionTextOf={conditionTextOf}
              onSelect={onSelect}
              onEditStep={onEditStep}
              onAddParallel={onAddParallel}
              onAddAfter={onAddAfter}
              parallelLabel={parallelLabel}
              nextLabel={nextLabel}
            />
          </div>
        ))}
        <Connector flowing={isRunning} />
        <GraphTerminal
          label={outputCount === 1 ? 'Output' : 'Outputs'}
          detail={`${outputCount} ${outputCount === 1 ? 'result' : 'results'}${hasRun ? ' · view' : ''}`}
          active={selected === 'outputs'}
          onClick={hasRun && onSelect ? () => onSelect('outputs') : undefined}
        />
      </div>
      <Legend
        conditions={nodes.some((node) => node.condition !== null)}
        reviews={loops.length > 0}
      />
    </div>
  );
}

interface StageColumnProps {
  stage: number;
  nodes: GraphNode[];
  selected: OutputTarget | null;
  /** A step's condition in words, for its node; null for a step without one. */
  conditionTextOf: (order: number) => string | null;
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
  conditionTextOf,
  onSelect,
  onEditStep,
  onAddParallel,
  onAddAfter,
  parallelLabel,
  nextLabel,
}: StageColumnProps) {
  return (
    // The width is fixed, so the loop-back lines above the stages line up with it.
    <motion.div
      className={`flex flex-col gap-3 ${columnWidth(nodes.length > 1)}`}
      {...stageEntrance(stage)}
    >
      <StageNodes {...{ stage, nodes, selected, conditionTextOf, onSelect, onEditStep }} />
      <StageActions {...{ stage, onAddParallel, onAddAfter, parallelLabel, nextLabel }} />
    </motion.div>
  );
}

type StageNodesProps = Pick<
  StageColumnProps,
  'stage' | 'nodes' | 'selected' | 'conditionTextOf' | 'onSelect' | 'onEditStep'
>;

function StageNodes({
  stage,
  nodes,
  selected,
  conditionTextOf,
  onSelect,
  onEditStep,
}: StageNodesProps) {
  const parallel = nodes.length > 1;
  return (
    <div className={`relative flex flex-col gap-3 ${parallel ? 'px-3' : ''}`}>
      <span className="absolute -top-6 right-0 left-0 text-center text-[10px] font-semibold tracking-wide text-slate-400 uppercase">
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
          conditionText={conditionTextOf(node.order)}
          onClick={
            SELECTABLE.has(node.status) && onSelect
              ? () => onSelect(node.order)
              : onEditStep
                ? () => onEditStep(node.order)
                : undefined
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
  stage,
  onAddParallel,
  onAddAfter,
  parallelLabel,
  nextLabel,
}: StageActionsProps) {
  if (!onAddParallel && !onAddAfter) return null;
  return (
    <div className="flex flex-wrap gap-2 text-[11px]">
      {onAddParallel && (
        <button
          type="button"
          onClick={() => onAddParallel(stage)}
          className="rounded-md border border-dashed border-sky-400/40 px-2 py-1 text-sky-300 hover:bg-sky-400/10"
        >
          {parallelLabel}
        </button>
      )}
      {onAddAfter && (
        <button
          type="button"
          onClick={() => onAddAfter(stage)}
          className="rounded-md border border-dashed border-white/20 px-2 py-1 text-slate-300 hover:bg-white/10"
        >
          {nextLabel}
        </button>
      )}
    </div>
  );
}

function Legend({ conditions, reviews }: { conditions: boolean; reviews: boolean }) {
  return (
    <div className="mt-4 flex flex-wrap items-center gap-4 text-[11px] text-slate-400">
      <span className="flex items-center gap-1.5">
        <OutputBadge /> result you receive
      </span>
      <span>If no output is marked, the last stage becomes the output.</span>
      <span>Stacked steps run in parallel.</span>
      {conditions && (
        <span className="flex items-center gap-1.5">
          <ConditionBadge /> runs only if its condition holds
        </span>
      )}
      {reviews && (
        <span className="flex items-center gap-1.5">
          <ReviewBadge /> can send the work back (the purple line)
        </span>
      )}
    </div>
  );
}

/** Arrow between columns; while a run is in flight a pulse of light travels along it. */
function Connector({ flowing }: { flowing: boolean }) {
  return (
    <div className={`mt-11 flex items-center ${CONNECTOR_WIDTH}`} aria-hidden="true">
      <span
        className={`h-px flex-1 ${
          flowing
            ? 'bg-[linear-gradient(90deg,#64748b_0%,#38bdf8_45%,#a855f7_55%,#64748b_100%)] bg-[length:200%_100%] motion-safe:animate-flow'
            : 'bg-slate-500'
        }`}
      />
      <span
        className={`border-y-4 border-l-[6px] border-y-transparent ${
          flowing ? 'border-l-sky-400' : 'border-l-slate-500'
        }`}
      />
    </div>
  );
}
