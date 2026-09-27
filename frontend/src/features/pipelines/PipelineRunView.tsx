import { useState, type ReactNode } from 'react';

import type { PipelineStep, StepResult } from '../../core/api/types';
import { OutputCard } from './OutputCard';
import { PipelineGraph } from './PipelineGraph';
import { RunResults } from './RunResults';
import { Spinner } from './Spinner';
import type { OutputTarget } from './pipelineGraph';

type Tab = 'final' | 'steps';

interface PipelineRunViewProps {
  steps: PipelineStep[];
  results: StepResult[];
  finalOutput: string;
  isRunning: boolean;
  input: string;
  elapsedMs: number | null;
}

/** The pipeline diagram plus the latest run's outputs; diagram nodes open outputs. */
export function PipelineRunView(props: PipelineRunViewProps) {
  const { steps, results, finalOutput, isRunning, input, elapsedMs } = props;
  const [tab, setTab] = useState<Tab>('final');
  const [focus, setFocus] = useState<OutputTarget | null>(null);
  const [shownResults, setShownResults] = useState(results);

  // A new run starts on its final output (React's "adjust state on prop change").
  if (shownResults !== results) {
    setShownResults(results);
    setTab('final');
    setFocus(null);
  }

  function select(target: OutputTarget) {
    setTab(target === 'final' ? 'final' : 'steps');
    setFocus(target);
  }

  return (
    <section>
      <PipelineGraph
        steps={steps}
        results={results}
        isRunning={isRunning}
        input={input}
        hasFinalOutput={Boolean(finalOutput)}
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
              <TabButton active={tab === 'final'} onClick={() => select('final')}>
                Final output
              </TabButton>
              <TabButton active={tab === 'steps'} onClick={() => setTab('steps')}>
                All steps ({results.length})
              </TabButton>
            </div>
            <RunStats results={results} elapsedMs={elapsedMs} />
          </div>

          {tab === 'final' ? (
            <OutputCard
              heading={<span className="text-lg font-semibold">Final output</span>}
              output={finalOutput}
              foldable={false}
            />
          ) : (
            <RunResults results={results} focusedStep={typeof focus === 'number' ? focus : null} />
          )}
        </div>
      )}
    </section>
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

function RunStats({ results, elapsedMs }: { results: StepResult[]; elapsedMs: number | null }) {
  const stageCount = new Set(results.map((result) => result.stage)).size;
  const parts = [`${results.length} steps`, `${stageCount} stages`];
  if (elapsedMs !== null) parts.push(`${(elapsedMs / 1000).toFixed(1)} s`);
  return <p className="text-xs text-slate-400">{parts.join(' · ')}</p>;
}
