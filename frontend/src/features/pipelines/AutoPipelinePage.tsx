import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useModels } from '../../core/hooks/useModels';
import { GeneratedSteps } from './GeneratedSteps';
import { PipelineGraph } from './PipelineGraph';
import { PipelineNav } from './PipelineNav';
import { Spinner } from './Spinner';
import { modelLabel } from './modelLabel';
import { useAutoPipeline } from './useAutoPipeline';

const cardClass = 'mb-8 rounded-2xl border border-white/10 bg-slate-800/50 p-8';

export function AutoPipelinePage() {
  const navigate = useNavigate();
  const { models, defaultModel, error: modelsError } = useModels();
  const { generated, status, errorMessage, successMessage, actions } = useAutoPipeline();
  const [description, setDescription] = useState('');
  const [plannerModel, setPlannerModel] = useState('');

  // The planner defaults to whatever the backend reports as its default model.
  useEffect(() => {
    if (defaultModel) setPlannerModel((current) => current || defaultModel);
  }, [defaultModel]);

  const isGenerating = status === 'generating';
  const isSaving = status === 'saving';

  async function handleSaveAndRun() {
    const stored = await actions.save();
    if (stored?.id !== undefined) navigate('/pipeline', { state: { pipelineId: stored.id } });
  }

  return (
    <div className="min-h-[calc(100vh-60px)] bg-slate-900 px-8 py-10 text-slate-50">
      <div className="mx-auto max-w-4xl">
        <header className="mb-8">
          <div className="mb-3 flex items-center gap-3">
            <span className="text-2xl font-extrabold">
              <span className="bg-gradient-to-r from-[#00d2ff] to-[#3a7bd5] bg-clip-text text-transparent">
                AI
              </span>
              Mix
            </span>
            <span className="text-sm text-slate-400">Auto Pipeline</span>
          </div>
          <PipelineNav />
          <p className="mt-3 text-sm text-slate-400">
            Describe your workflow and the outputs you need. Review the generated stages before
            saving. Each step runs as an agent with your configured MCP tools.
          </p>
        </header>

        <section className={cardClass}>
          <h2 className="mb-4 text-xl font-semibold">Describe Your Workflow</h2>
          <textarea
            value={description}
            disabled={isGenerating}
            placeholder="Example: Analyze this product idea, then produce a launch email and three social posts in parallel. Finish with a short summary."
            onChange={(event) => setDescription(event.target.value)}
            className="mb-4 h-32 w-full resize-y rounded-lg border border-white/10 bg-slate-900 p-4 text-sm outline-none focus:border-sky-400 disabled:opacity-60"
          />

          <div className="flex flex-wrap items-end gap-4">
            <div>
              <label htmlFor="planner" className="mb-1 block text-xs text-slate-400">
                Planner Model:
              </label>
              <select
                id="planner"
                value={plannerModel}
                disabled={isGenerating}
                onChange={(event) => setPlannerModel(event.target.value)}
                className="rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm outline-none focus:border-sky-400"
              >
                {models.map((model) => (
                  <option key={model} value={model}>
                    {modelLabel(model)}
                  </option>
                ))}
              </select>
            </div>

            <button
              type="button"
              onClick={() => void actions.generate(description, plannerModel)}
              disabled={isGenerating || !description.trim()}
              className="flex items-center gap-2 rounded-lg bg-gradient-to-br from-sky-500 to-indigo-500 px-6 py-3 font-semibold text-white transition-transform hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0"
            >
              {isGenerating && <Spinner className="size-4" />}
              {isGenerating ? 'Generating…' : 'Generate Pipeline'}
            </button>
          </div>

          {(errorMessage || modelsError) && (
            <p className="mt-4 rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-300">
              {errorMessage || modelsError}
            </p>
          )}
          {successMessage && (
            <p className="mt-4 rounded-lg bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">
              {successMessage}
            </p>
          )}
        </section>

        {isGenerating && (
          <div className="mb-8 flex flex-col items-center gap-3 text-slate-400">
            <Spinner />
            <p>AI is analyzing your workflow and creating pipeline steps…</p>
          </div>
        )}

        {generated && !isGenerating && (
          <section inert={isSaving} className={cardClass}>
            <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
              <h2 className="text-xl font-semibold">Generated Pipeline</h2>
              <input
                type="text"
                value={generated.name}
                placeholder="Pipeline Name"
                onChange={(event) => actions.rename(event.target.value)}
                className="rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm outline-none focus:border-sky-400"
              />
            </div>

            <div className="mb-6">
              <PipelineGraph
                steps={generated.steps}
                onAddParallel={(stage) => actions.addOutput(stage, true)}
                onAddAfter={(stage) => actions.addOutput(stage, false)}
                parallelLabel="+ Parallel output"
                nextLabel="+ Next output"
              />
              <p className="mt-2 text-xs text-slate-400">
                Added outputs need a prompt before saving. Edit the cards below to define each result.
              </p>
            </div>

            <GeneratedSteps
              pipeline={generated}
              availableModels={models}
              onChange={actions.patchStep}
              onRemove={actions.removeStep}
            />

            <div className="mt-6 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={actions.reset}
                className="rounded-lg border border-white/10 bg-white/5 px-5 py-3 text-sm transition-colors hover:bg-white/10"
              >
                Start Over
              </button>
              <button
                type="button"
                onClick={() => void actions.save()}
                disabled={isSaving}
                className="rounded-lg bg-sky-500 px-5 py-3 text-sm font-semibold transition-colors hover:bg-sky-400 disabled:opacity-60"
              >
                {isSaving ? 'Saving…' : 'Save Pipeline'}
              </button>
              <button
                type="button"
                onClick={() => void handleSaveAndRun()}
                disabled={isSaving}
                className="rounded-lg bg-gradient-to-br from-sky-500 to-indigo-500 px-5 py-3 text-sm font-semibold transition-colors disabled:opacity-60"
              >
                {isSaving ? 'Saving…' : 'Save & Open Builder'}
              </button>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
