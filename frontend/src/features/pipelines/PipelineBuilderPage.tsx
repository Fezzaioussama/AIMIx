import { useState } from 'react';

import { useModels } from '../../core/hooks/useModels';
import { PipelineNav } from './PipelineNav';
import { RunResults } from './RunResults';
import { Spinner } from './Spinner';
import { StepEditor } from './StepEditor';
import { usePipelineBuilder } from './usePipelineBuilder';

export function PipelineBuilderPage() {
  const { models, defaultModel, error: modelsError } = useModels();
  const { pipeline, saved, results, finalOutput, status, message, actions } =
    usePipelineBuilder(defaultModel);
  const [input, setInput] = useState('');

  const isSaving = status === 'saving';
  const isRunning = status === 'running';

  return (
    <div className="flex h-[calc(100vh-60px)] bg-slate-900 text-slate-50">
      <aside className="flex w-[350px] shrink-0 flex-col overflow-y-auto border-r border-white/10 bg-slate-800/70 p-6 backdrop-blur-xl">
        <div className="mb-4 text-lg font-extrabold">
          <span className="bg-gradient-to-r from-[#00d2ff] to-[#3a7bd5] bg-clip-text text-transparent">
            AI
          </span>
          Mix Pipeline
        </div>
        <div className="mb-6">
          <PipelineNav />
        </div>

        <button
          type="button"
          onClick={actions.reset}
          className="mb-3 w-full rounded-md border border-white/10 bg-white/5 px-3 py-2 text-sm transition-colors hover:bg-white/10"
        >
          + Create New
        </button>
        <input
          type="text"
          value={pipeline.name}
          placeholder="Pipeline Name"
          onChange={(event) => actions.rename(event.target.value)}
          className="mb-3 w-full rounded-md border border-white/10 bg-slate-900 px-3 py-2 text-sm outline-none focus:border-sky-400"
        />
        <button
          type="button"
          onClick={() => void actions.save()}
          disabled={isSaving}
          className={`mb-6 w-full rounded-md px-3 py-2 text-sm font-semibold transition-colors disabled:opacity-60 ${
            pipeline.id === undefined
              ? 'bg-sky-500 hover:bg-sky-400'
              : 'bg-emerald-600 hover:bg-emerald-500'
          }`}
        >
          {isSaving ? 'Saving…' : pipeline.id === undefined ? 'Save Pipeline' : 'Save Changes'}
        </button>

        <h3 className="mb-2 text-xs font-semibold tracking-wide text-slate-400 uppercase">
          Recent Pipelines
        </h3>
        <div className="mb-6">
          {saved.map((candidate) => (
            <button
              key={candidate.id}
              type="button"
              onClick={() => actions.select(candidate)}
              className={`mb-2 flex w-full items-center justify-between rounded-md border px-3 py-2 text-left text-sm transition-colors ${
                candidate.id === pipeline.id
                  ? 'border-sky-400/30 bg-sky-400/10 text-sky-300'
                  : 'border-white/10 bg-white/5 hover:bg-white/10'
              }`}
            >
              {candidate.name}
              <span className="text-xs text-slate-400">{candidate.steps.length} steps</span>
            </button>
          ))}
        </div>

        <h3 className="mb-2 text-xs font-semibold tracking-wide text-slate-400 uppercase">
          Workflow Steps
        </h3>
        <StepEditor
          steps={pipeline.steps}
          availableModels={models}
          onChange={actions.patchStep}
          onRemove={actions.removeStep}
        />
        <button
          type="button"
          onClick={actions.addStep}
          className="w-full rounded-md border border-dashed border-white/20 px-3 py-2 text-sm text-slate-300 transition-colors hover:border-sky-400/40 hover:text-sky-300"
        >
          + Add Next Step
        </button>
      </aside>

      <main className="flex-1 overflow-y-auto p-12">
        <div className="mx-auto max-w-4xl">
          <div className="mb-8 rounded-2xl border border-white/10 bg-slate-800/50 p-8">
            <h2 className="mb-4 text-xl font-semibold">Run Execution</h2>
            <textarea
              value={input}
              placeholder="Enter your initial input here..."
              onChange={(event) => setInput(event.target.value)}
              className="mb-4 h-28 w-full resize-y rounded-lg border border-white/10 bg-slate-900 p-4 text-sm outline-none focus:border-sky-400"
            />
            <button
              type="button"
              onClick={() => void actions.run(input)}
              disabled={isRunning || !input.trim()}
              className="rounded-lg bg-gradient-to-br from-sky-500 to-indigo-500 px-8 py-4 font-semibold text-white transition-transform hover:-translate-y-0.5 hover:shadow-[0_6px_20px_rgba(99,102,241,0.4)] disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0"
            >
              {isRunning ? 'Executing…' : 'Run Pipeline'}
            </button>
            {(message || modelsError) && (
              <p className="mt-4 text-sm text-amber-300">{message || modelsError}</p>
            )}
          </div>

          {isRunning && (
            <div className="mb-8 flex flex-col items-center gap-3 text-slate-400">
              <Spinner />
              <p>Processing pipeline steps…</p>
            </div>
          )}

          <RunResults results={results} finalOutput={finalOutput} />
        </div>
      </main>
    </div>
  );
}
