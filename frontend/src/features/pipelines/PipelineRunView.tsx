import { useState, type ReactNode } from 'react';

import type { PipelineStep, StepResult } from '../../core/api/types';
import { OutputCard } from './OutputCard';
import { PipelineGraph } from './PipelineGraph';
import { RunResults } from './RunResults';
import { Spinner } from './Spinner';
import { StepHeading } from './StepHeading';
import type { OutputTarget } from './pipelineGraph';

type Tab = 'outputs' | 'steps';

interface PipelineRunViewProps {
  steps: PipelineStep[];
  results: StepResult[];
  isRunning: boolean;
  input: string;
  elapsedMs: number | null;
}

/** The pipeline diagram plus the latest run's outputs; diagram nodes open outputs. */
export function PipelineRunView({
  steps,
  results,
  isRunning,
  input,
  elapsedMs,
}: PipelineRunViewProps) {
  const [tab, setTab] = useState<Tab>('outputs');
  const [focus, setFocus] = useState<OutputTarget | null>(null);
  const [shownResults, setShownResults] = useState(results);
  const outputs = results.filter((result) => result.is_output);

  // A new run starts on its outputs (React's "adjust state on prop change").
  if (shownResults !== results) {
    setShownResults(results);
    setTab('outputs');
    setFocus(null);
  }

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
        results={results}
        isRunning={isRunning}
        input={input}
        selected={focus}
        onSelect={select}
      />

      {isRunning && (
        <div className="mt-8 flex flex-col items-center gap-3 text-slate-400">
          <Spinner />
          <p>Running the pipeline — parallel steps run at the same time…</p>
        </div>
      )}

      {results.length > 0 && !isRunning && (
        <div className="mt-8">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex gap-1 rounded-lg bg-slate-800/70 p-1" role="tablist">
              <TabButton active={tab === 'outputs'} onClick={() => setTab('outputs')}>
                Outputs ({outputs.length})
              </TabButton>
              <TabButton active={tab === 'steps'} onClick={() => setTab('steps')}>
                All steps ({results.length})
              </TabButton>
            </div>
            <RunStats results={results} outputCount={outputs.length} elapsedMs={elapsedMs} />
          </div>

          {tab === 'outputs' ? (
            <OutputsPanel outputs={outputs} focusedStep={focusedStep} />
          ) : (
            <RunResults results={results} focusedStep={focusedStep} />
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
  const single = outputs.length === 1;
  return (
    <div className={single ? '' : 'grid gap-4 xl:grid-cols-2'}>
      {outputs.map((result) => (
        <OutputCard
          key={result.step_order}
          heading={<StepHeading result={result} />}
          output={result.output}
          input={result.input_used}
          highlighted={focusedStep === result.step_order}
          foldable={!single}
        />
      ))}
    </div>
  );
}

interface TabButtonProps {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}

function TabButton({ active, onClick, children }: TabButtonProps) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`rounded-md px-4 py-1.5 text-sm font-medium transition-colors ${
        active ? 'bg-sky-500 text-white' : 'text-slate-300 hover:bg-white/10'
      }`}
    >
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
  const parts = [
    `${outputCount} ${outputCount === 1 ? 'output' : 'outputs'}`,
    `${results.length} steps`,
    `${stageCount} stages`,
  ];
  if (elapsedMs !== null) parts.push(`${(elapsedMs / 1000).toFixed(1)} s`);
  return <p className="text-xs text-slate-400">{parts.join(' · ')}</p>;
}
