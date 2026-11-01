import { Users } from 'lucide-react';
import { useMemo } from 'react';

import type { Run, RunStep } from '../../../core/api/types';
import { Heading, type HeadingLevel } from '../../../core/ui/Heading';
import { countOf } from '../../../core/usageFormat';
import { Foldable, PanelToggle } from '../../pipelines/FoldablePanel';
import { PipelineGraph } from '../../pipelines/PipelineGraph';
import { groupByStage } from '../../pipelines/stages';
import { isActive } from '../runStatus';
import { inRunOrder, type ReportModel } from './reportModel';
import { givenParts } from './runGiven';
import { RunGiven } from './RunGiven';
import { TimelineRow, type RowRole } from './TimelineRow';

const SUBHEADING = 'text-sm font-semibold text-white';

/** What each step made, as its row in the timeline links to it. */
function roleOf(step: RunStep, model: ReportModel): RowRole {
  const order = step.step_order;
  if (model.reviewer?.step.step_order === order) return 'reviewer';
  return model.deliverables.some((view) => view.step.step_order === order) ? 'deliverable' : 'work';
}

interface TimelineProps {
  run: Run;
  model: ReportModel;
  level: 2 | 3;
  onReadCheck: () => void;
}

/** "What each agent did": a row per agent, by stage; a stage of several says they ran at once. */
function Timeline({ run, model, level, onReadCheck }: TimelineProps) {
  const stages = groupByStage(inRunOrder(run.steps), (step) => step.stage);
  return (
    <div className="mt-1 space-y-3">
      {stages.map(({ stage, items }) => (
        <div key={stage}>
          {items.length > 1 && (
            <p className="mt-2 text-xs text-slate-400">Stage {stage} · at the same time</p>
          )}
          <ul className="divide-y divide-white/[0.06]">
            {items.map((step) => (
              <TimelineRow
                key={step.step_order}
                run={run}
                step={step}
                role={roleOf(step, model)}
                level={level}
                onReadCheck={onReadCheck}
              />
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

/** "The team": the run's own diagram, read-only, with each agent in its run status. */
function TeamDiagram({ run, level }: { run: Run; level: 2 | 3 }) {
  return (
    <>
      <Heading level={(level + 1) as HeadingLevel} className={`mt-6 mb-3 ${SUBHEADING}`}>
        The team
      </Heading>
      <PipelineGraph
        steps={run.definition.steps}
        inputs={run.definition.inputs}
        liveSteps={run.steps}
        isRunning={isActive(run.status)}
        input={run.input}
      />
    </>
  );
}

interface TeamWorkProps extends TimelineProps {
  open: boolean;
  onToggle: () => void;
  /** The team's diagram as a last part, where it is not on the screen already. */
  diagram: boolean;
}

/**
 * "How your team got there", folded away at first: what each agent did, what the team
 * was given and, on the Runs page, the team's diagram. Every output it links to is shown
 * once on the page, above or folded in its row.
 */
export function TeamWork({
  run,
  model,
  level,
  open,
  onToggle,
  diagram,
  onReadCheck,
}: TeamWorkProps) {
  const parts = useMemo(() => givenParts(run), [run]);
  const stages = new Set(run.steps.map((step) => step.stage)).size;
  const sub = (level + 1) as HeadingLevel;
  const id = `run-${run.id}-team`;
  return (
    <section className="rounded-2xl border border-white/10 bg-white/[0.02]">
      <PanelToggle
        id={id}
        level={level}
        icon={<Users aria-hidden="true" className="size-4 shrink-0 text-sky-300" />}
        title="How your team got there"
        summary={`${countOf(run.steps.length, 'agent')} · ${countOf(stages, 'stage')}`}
        open={open}
        onToggle={onToggle}
      />
      <Foldable id={`${id}-body`} open={open} size="large">
        <Heading level={sub} className={SUBHEADING}>
          What each agent did
        </Heading>
        <Timeline run={run} model={model} level={level} onReadCheck={onReadCheck} />
        {parts.length > 0 && (
          <>
            <Heading level={sub} className={`mt-6 ${SUBHEADING}`}>
              What your team was given
            </Heading>
            <RunGiven parts={parts} level={level} />
          </>
        )}
        {diagram && <TeamDiagram run={run} level={level} />}
      </Foldable>
    </section>
  );
}
