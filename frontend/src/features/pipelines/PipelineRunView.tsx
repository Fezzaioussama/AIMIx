import { useState, type ReactNode } from 'react';

import type { PipelineInput, PipelineStep, RunStep, StepResult } from '../../core/api/types';
import { ActivePill } from '../../core/ui/ActivePill';
import { BusyNotice } from '../../core/ui/BusyNotice';
import { AnimatedContent } from '../../core/ui/reactbits/AnimatedContent';
import { CountUp } from '../../core/ui/reactbits/CountUp';
import { OutputCard } from './OutputCard';
import { PipelineGraph } from './PipelineGraph';
import { RunResults } from './RunResults';
import { StepHeading } from './StepHeading';
import type { OutputTarget } from './pipelineGraph';
import { groupByStage } from './stages';

type Tab = 'outputs' | 'steps';

const TAB_LIST = 'flex gap-1 rounded-xl border border-white/10 bg-slate-900/70 p-1';
const NO_RESULTS: StepResult[] = [];

interface PipelineRunViewProps {
  steps: PipelineStep[];
  inputs?: PipelineInput[];
  /** The latest finished results; ignored while `liveSteps` are shown. */
  results?: StepResult[];
  /** A followed run's steps with their progress: nodes show each step's status,
   * and an output appears as soon as it is saved. */
  liveSteps?: RunStep[];
  /** Which run `liveSteps` belong to; the view starts over when another replaces it. */
  runKey?: number | null;
  isRunning: boolean;
  input: string;
  elapsedMs: number | null;
  onEditStep?: (order: number) => void;
  onAddParallel?: (stage: number) => void;
  onAddAfter?: (stage: number) => void;
  children?: ReactNode;
}

/** The pipeline diagram plus the latest run's outputs; diagram nodes open outputs. */
export function PipelineRunView({
  steps,
  inputs,
  results: finished = NO_RESULTS,
  liveSteps,
  runKey = null,
  isRunning,
  input,
  elapsedMs,
  onEditStep,
  onAddParallel,
  onAddAfter,
  children,
}: PipelineRunViewProps) {
  const results = liveSteps ? liveSteps.filter((step) => step.status === 'succeeded') : finished;
  const outputs = results.filter((result) => result.is_output);
  const shownRun = liveSteps ? runKey : finished;
  const [tab, setTab] = useState<Tab>(liveSteps && isRunning ? 'steps' : 'outputs');
  const [focus, setFocus] = useState<OutputTarget | null>(null);
  const [seenRun, setSeenRun] = useState(shownRun);
  const [wasRunning, setWasRunning] = useState(isRunning);

  // React's "adjust state on prop change": a new run starts on its progress
  // while it runs, on its outputs once done; a followed run that finishes
  // turns to its outputs.
  if (seenRun !== shownRun) {
    setSeenRun(shownRun);
    setWasRunning(isRunning);
    setTab(liveSteps && isRunning ? 'steps' : 'outputs');
    setFocus(null);
  } else if (wasRunning !== isRunning) {
    setWasRunning(isRunning);
    if (!isRunning && outputs.length > 0) setTab('outputs');
  }
  const hasResults = liveSteps ? liveSteps.length > 0 : results.length > 0 && !isRunning;

  function select(target: OutputTarget) {
    const isOutput = target === 'outputs' || outputs.some((r) => r.step_order === target);
    setTab(isOutput ? 'outputs' : 'steps');
    setFocus(target);
  }

  const focusedStep = typeof focus === 'number' ? focus : null;

  return (
    <section>
      <PipelineGraph
        steps={steps}
        inputs={inputs}
        results={results}
        liveSteps={liveSteps}
        isRunning={isRunning}
        input={input}
        selected={focus}
        onSelect={select}
        onEditStep={onEditStep}
        onAddParallel={onAddParallel}
        onAddAfter={onAddAfter}
      />

      {children}

      {isRunning && !liveSteps && (
        <BusyNotice className="mt-8">
          Running the pipeline — parallel steps run at the same time…
        </BusyNotice>
      )}

      {hasResults && (
        <div className="mt-8">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div className={TAB_LIST} role="tablist">
              <TabButton value="outputs" active={tab === 'outputs'} onClick={setTab}>
                Outputs ({outputs.length})
              </TabButton>
              <TabButton value="steps" active={tab === 'steps'} onClick={setTab}>
                All steps ({liveSteps?.length ?? results.length})
              </TabButton>
            </div>
            {/* Totals count up once the run has ended; the status bar tracks progress. */}
            {!isRunning && (
              <RunStats results={results} outputCount={outputs.length} elapsedMs={elapsedMs} />
            )}
          </div>

          {tab === 'outputs' ? (
            <OutputsPanel outputs={outputs} focusedStep={focusedStep} />
          ) : (
            <RunResults
              results={liveSteps ?? results}
              focusedStep={focusedStep}
              runActive={isRunning}
            />
          )}
        </div>
      )}
    </section>
  );
}

function OutputsPanel({
  outputs,
  focusedStep,
}: {
  outputs: StepResult[];
  focusedStep: number | null;
}) {
  const stages = groupByStage(outputs, (result) => result.stage);
  if (stages.length === 0) {
    return (
      <p className="rounded-2xl border border-dashed border-white/10 p-6 text-sm text-slate-400">
        No outputs yet. Each one appears here as soon as it is ready.
      </p>
    );
  }
  return (
    <div className="space-y-6">
      {stages.map((group) => (
        <section key={group.stage} aria-label={`Stage ${group.stage} outputs`}>
          <h3 className="mb-3 text-sm font-semibold text-slate-300">
            Stage {group.stage}{' '}
            <span className="text-slate-400">
              · {group.items.length} {group.items.length === 1 ? 'output' : 'outputs'}
            </span>
          </h3>
          <div className={group.items.length > 1 ? 'grid gap-4 xl:grid-cols-2' : ''}>
            {group.items.map((result, index) => (
              <AnimatedContent key={result.step_order} distance={18} delay={index * 0.08}>
                <OutputCard
                  heading={<StepHeading result={result} />}
                  output={result.output}
                  input={result.input_used}
                  highlighted={focusedStep === result.step_order}
                  foldable={outputs.length > 1}
                />
              </AnimatedContent>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

interface TabButtonProps {
  value: Tab;
  active: boolean;
  onClick: (value: Tab) => void;
  children: ReactNode;
}

/** A results tab; the active one carries the gliding `run-tabs` pill. */
function TabButton({ value, active, onClick, children }: TabButtonProps) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={() => onClick(value)}
      className={`relative isolate rounded-lg px-4 py-1.5 text-sm font-medium transition-colors ${
        active ? 'text-white' : 'text-slate-300 hover:text-white'
      }`}
    >
      {active && (
        <ActivePill
          layoutId="run-tabs"
          // Per tab: the pill glides when the tab changes, but not after the
          // tab list when a live run's status bar above it changes height.
          layoutDependency={value}
          className="bg-gradient-to-r from-sky-500 to-indigo-500 shadow-[0_6px_20px_-8px_rgba(99,102,241,0.9)]"
        />
      )}
      {children}
    </button>
  );
}

interface RunStatsProps {
  results: StepResult[];
  outputCount: number;
  elapsedMs: number | null;
}

function RunStats({ results, outputCount, elapsedMs }: RunStatsProps) {
  const stageCount = new Set(results.map((result) => result.stage)).size;
  const stats = [
    { value: outputCount, label: outputCount === 1 ? 'output' : 'outputs', decimals: 0 },
    { value: results.length, label: 'steps', decimals: 0 },
    { value: stageCount, label: 'stages', decimals: 0 },
  ];
  if (elapsedMs !== null) stats.push({ value: elapsedMs / 1000, label: 's', decimals: 1 });
  const summary = stats
    .map((stat) => `${stat.value.toFixed(stat.decimals)} ${stat.label}`)
    .join(' · ');

  // The counting chips are visual; assistive tech reads the one-line summary.
  return (
    <div className="text-xs text-slate-400">
      <p className="sr-only">{summary}</p>
      <div aria-hidden="true" className="flex flex-wrap gap-2">
        {stats.map((stat) => (
          <span
            key={stat.label}
            className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1"
          >
            <CountUp
              to={stat.value}
              decimals={stat.decimals}
              className="font-semibold text-slate-100"
            />{' '}
            {stat.label}
          </span>
        ))}
      </div>
    </div>
  );
}
