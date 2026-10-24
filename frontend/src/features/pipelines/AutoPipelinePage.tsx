import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useModels } from '../../core/hooks/useModels';
import { useAgentTools } from '../../core/hooks/useAgentTools';
import { BrandMark } from '../../core/ui/BrandMark';
import { BusyNotice } from '../../core/ui/BusyNotice';
import { GlowButton } from '../../core/ui/GlowButton';
import { AnimatedContent } from '../../core/ui/reactbits/AnimatedContent';
import { ShinyText } from '../../core/ui/reactbits/ShinyText';
import { SpotlightCard } from '../../core/ui/reactbits/SpotlightCard';
import { GeneratedSteps } from './GeneratedSteps';
import { PipelineGraph } from './PipelineGraph';
import { PipelineInputsEditor } from './PipelineInputsEditor';
import { PipelineNav } from './PipelineNav';
import { modelLabel } from './modelLabel';
import { useAutoPipeline } from './useAutoPipeline';

const cardClass = 'mb-8 p-8';
const fieldClass =
  'rounded-lg border border-white/10 bg-slate-950/60 px-3 py-2 text-sm transition-[border-color,box-shadow] outline-none focus:border-sky-400/60 focus:shadow-[0_0_0_3px_rgba(56,189,248,0.12)]';

export function AutoPipelinePage() {
  const navigate = useNavigate();
  const { models, defaultModel, error: modelsError } = useModels();
  const { tools, error: toolsError } = useAgentTools();
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
    <div className="min-h-[calc(100vh-60px)] px-4 py-10 text-slate-50 sm:px-8">
      <div className="mx-auto max-w-4xl">
        <header className="mb-8">
          <div className="mb-3 flex items-baseline gap-3">
            <BrandMark />
            <ShinyText className="text-sm text-slate-400/70">Auto Pipeline</ShinyText>
          </div>
          <PipelineNav />
          <p className="mt-3 text-sm text-slate-400">
            Describe your workflow, what you will provide on each run, and the outputs you need.
            Review the generated inputs and stages before saving. Give each agent a role, the
            output it must deliver, and the tools it can use.
          </p>
        </header>

        <SpotlightCard as="section" className={cardClass}>
          <h2 className="mb-4 text-xl font-semibold">Describe Your Workflow</h2>
          <textarea
            value={description}
            disabled={isGenerating}
            placeholder="Example: Analyze this product idea, then produce a launch email and three social posts in parallel. Finish with a short summary."
            onChange={(event) => setDescription(event.target.value)}
            className={`mb-4 h-32 w-full resize-y p-4 disabled:opacity-60 ${fieldClass}`}
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
                className={fieldClass}
              >
                {models.map((model) => (
                  <option key={model} value={model}>
                    {modelLabel(model)}
                  </option>
                ))}
              </select>
            </div>

            <GlowButton
              onClick={() => void actions.generate(description, plannerModel)}
              busy={isGenerating}
              disabled={!description.trim()}
            >
              {isGenerating ? 'Generating…' : 'Generate Pipeline'}
            </GlowButton>
          </div>

          {(errorMessage || modelsError || toolsError) && (
            <p className="mt-4 rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-300">
              {errorMessage || modelsError || toolsError}
            </p>
          )}
          {successMessage && (
            <p className="mt-4 rounded-lg bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">
              {successMessage}
            </p>
          )}
        </SpotlightCard>

        {isGenerating && (
          <BusyNotice className="mb-8">
            AI is analyzing your workflow and creating pipeline steps…
          </BusyNotice>
        )}

        {generated && !isGenerating && (
          <AnimatedContent distance={30}>
            <SpotlightCard as="section" inert={isSaving} className={cardClass}>
              <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
                <h2 className="text-xl font-semibold">Generated Pipeline</h2>
                <input
                  type="text"
                  value={generated.name}
                  placeholder="Pipeline Name"
                  onChange={(event) => actions.rename(event.target.value)}
                  className={fieldClass}
                />
              </div>

              <div className="mb-6">
                <PipelineGraph
                  steps={generated.steps}
                  inputs={generated.inputs}
                  onAddParallel={(stage) => actions.addOutput(stage, true)}
                  onAddAfter={(stage) => actions.addOutput(stage, false)}
                  parallelLabel="+ Parallel output"
                  nextLabel="+ Next output"
                />
                <p className="mt-2 text-xs text-slate-400">
                  Added outputs need a prompt before saving. Edit the cards below to define each
                  result.
                </p>
              </div>

              <section aria-label="Run inputs" className="mb-6">
                <h3 className="mb-1 text-sm font-semibold text-slate-200">Run inputs</h3>
                <p className="mb-3 text-xs text-slate-400">
                  What you fill in on every run. Any step can use one as {'{name}'}.
                </p>
                <div className="max-w-md">
                  <PipelineInputsEditor inputs={generated.inputs} onChange={actions.setInputs} />
                </div>
              </section>

              <GeneratedSteps
                pipeline={generated}
                availableModels={models}
                availableTools={tools}
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
                  className="rounded-xl bg-sky-500 px-5 py-3 text-sm font-semibold transition-colors hover:bg-sky-400 disabled:opacity-60"
                >
                  {isSaving ? 'Saving…' : 'Save Pipeline'}
                </button>
                <GlowButton onClick={() => void handleSaveAndRun()} busy={isSaving}>
                  {isSaving ? 'Saving…' : 'Save & Open Builder'}
                </GlowButton>
              </div>
            </SpotlightCard>
          </AnimatedContent>
        )}
      </div>
    </div>
  );
}
