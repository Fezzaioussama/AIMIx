import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';

import { useModels } from '../../core/hooks/useModels';
import { useAgentTools } from '../../core/hooks/useAgentTools';
import { elapsedMs } from '../../core/time';
import { BrandMark } from '../../core/ui/BrandMark';
import { CountUp } from '../../core/ui/reactbits/CountUp';
import { ShinyText } from '../../core/ui/reactbits/ShinyText';
import { LiveRunHeader } from '../runs/LiveRunHeader';
import { isActive, ranThisVersion } from '../runs/runStatus';
import { useLatestRun } from '../runs/useLatestRun';
import { PipelineInputsEditor } from './PipelineInputsEditor';
import { PipelineNav } from './PipelineNav';
import { PipelineRunView } from './PipelineRunView';
import { RecentPipelines } from './RecentPipelines';
import { RunInputCard } from './RunInputCard';
import { StepEditor } from './StepEditor';
import { EMPTY_RUN_DRAFT, type RunDraft } from './pipelineInputs';
import { usePipelineBuilder } from './usePipelineBuilder';

export function PipelineBuilderPage() {
  const routeState: unknown = useLocation().state;
  const initialId =
    routeState !== null &&
    typeof routeState === 'object' &&
    'pipelineId' in routeState &&
    typeof routeState.pipelineId === 'number'
      ? routeState.pipelineId
      : undefined;
  const { models, defaultModel, error: modelsError } = useModels();
  const { tools, error: toolsError } = useAgentTools();
  const { pipeline, saved, status, message, dirty, actions } = usePipelineBuilder(
    defaultModel,
    typeof initialId === 'number' ? initialId : undefined,
  );
  const [draft, setDraft] = useState<RunDraft>(EMPTY_RUN_DRAFT);
  // The pipeline's newest run, followed live; reopening the pipeline shows it again.
  const latest = useLatestRun(pipeline.id);
  const run = latest.run;
  // The diagram shows the run only if it executed exactly what is on screen.
  const shown = run !== null && !dirty && ranThisVersion(run, pipeline) ? run : null;

  const isSaving = status === 'saving';
  const isStarting = status === 'running';
  const isRunning = isStarting || (run !== null && isActive(run.status));
  const shownActive = shown !== null && isActive(shown.status);
  const stageCount = new Set(pipeline.steps.map((step) => step.stage)).size;

  function editStep(order: number) {
    document.getElementById(`step-editor-${order}`)?.scrollIntoView?.({ behavior: 'smooth' });
  }

  async function startRun() {
    const started = await actions.run(draft);
    if (started) latest.follow(started);
  }

  return (
    <div className="flex min-h-[calc(100vh-60px)] flex-col text-slate-50 lg:h-[calc(100vh-60px)] lg:flex-row">
      <aside
        inert={isStarting || isSaving}
        className="flex max-h-[45vh] w-full shrink-0 flex-col overflow-y-auto border-b border-white/10 bg-slate-950/60 p-6 backdrop-blur-xl lg:max-h-none lg:w-[350px] lg:border-r lg:border-b-0"
      >
        <div className="mb-4 flex items-baseline gap-2">
          <BrandMark className="text-lg" />
          <span className="text-lg font-extrabold text-slate-200">Pipeline</span>
        </div>
        <div className="mb-6">
          <PipelineNav />
        </div>

        <button
          type="button"
          onClick={actions.reset}
          className="mb-3 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm transition-colors hover:border-sky-400/30 hover:bg-white/10"
        >
          + Create New
        </button>
        <input
          type="text"
          value={pipeline.name}
          placeholder="Pipeline Name"
          onChange={(event) => actions.rename(event.target.value)}
          className="mb-3 w-full rounded-lg border border-white/10 bg-slate-950/60 px-3 py-2 text-sm transition-[border-color,box-shadow] outline-none focus:border-sky-400/60 focus:shadow-[0_0_0_3px_rgba(56,189,248,0.12)]"
        />
        <button
          type="button"
          onClick={() => void actions.save()}
          disabled={isSaving}
          className={`mb-6 w-full rounded-lg px-3 py-2 text-sm font-semibold transition-[background-color,box-shadow] disabled:opacity-60 ${
            pipeline.id === undefined
              ? 'bg-sky-500 hover:bg-sky-400 hover:shadow-[0_6px_20px_-8px_rgba(56,189,248,0.8)]'
              : 'bg-emerald-600 hover:bg-emerald-500 hover:shadow-[0_6px_20px_-8px_rgba(16,185,129,0.8)]'
          }`}
        >
          {isSaving ? 'Saving…' : pipeline.id === undefined ? 'Save Pipeline' : 'Save Changes'}
        </button>

        <h3 className="mb-2 text-xs font-semibold tracking-wide text-slate-400 uppercase">
          Recent Pipelines
        </h3>
        <RecentPipelines pipelines={saved} activeId={pipeline.id} onSelect={actions.select} />

        <h3 className="mb-2 text-xs font-semibold tracking-wide text-slate-400 uppercase">
          Run Inputs
        </h3>
        <p className="mb-3 text-xs text-slate-400">
          Named values you fill in on every run. Any step, in any stage, can use one as {'{name}'}.
        </p>
        <div className="mb-6">
          <PipelineInputsEditor inputs={pipeline.inputs} onChange={actions.setInputs} />
        </div>

        <h3 className="mb-2 text-xs font-semibold tracking-wide text-slate-400 uppercase">
          Workflow Steps
        </h3>
        <p className="mb-3 text-xs text-slate-400">
          Each step is an agent. Give it a role, prompt, the output it must deliver, and access to
          the tools it needs. Choose Output for each result you want.
        </p>
        {toolsError && <p className="mb-3 text-xs text-amber-300">{toolsError}</p>}
        <StepEditor
          steps={pipeline.steps}
          inputs={pipeline.inputs}
          availableModels={models}
          availableTools={tools}
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

      <main className="min-w-0 flex-1 overflow-y-auto p-4 sm:p-8 lg:p-12">
        <div className="mx-auto max-w-6xl">
          <div className="mb-8">
            <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="mb-1 text-xs font-semibold tracking-widest uppercase">
                  <ShinyText className="text-sky-400/80">Workflow canvas</ShinyText>
                </p>
                <h1 className="text-2xl font-bold tracking-tight">
                  {pipeline.name || 'New Pipeline'}
                </h1>
              </div>
              <p className="text-sm text-slate-400">
                <CountUp to={stageCount} duration={0.6} className="font-semibold text-slate-200" />{' '}
                {stageCount === 1 ? 'stage' : 'stages'} ·{' '}
                <CountUp
                  to={pipeline.steps.length}
                  duration={0.6}
                  className="font-semibold text-slate-200"
                />{' '}
                {pipeline.steps.length === 1 ? 'step' : 'steps'}
              </p>
            </div>
            <PipelineRunView
              steps={pipeline.steps}
              inputs={pipeline.inputs}
              liveSteps={shown?.steps}
              runKey={shown?.id ?? null}
              isRunning={shown ? shownActive : isStarting}
              input={draft.text}
              elapsedMs={
                shown && !shownActive
                  ? elapsedMs(shown.started_at, shown.finished_at, Date.now())
                  : null
              }
              onEditStep={isRunning || isSaving ? undefined : editStep}
              onAddParallel={isRunning || isSaving ? undefined : actions.addParallelStep}
              onAddAfter={isRunning || isSaving ? undefined : actions.addStepAfter}
            >
              <RunInputCard
                inputs={pipeline.inputs}
                draft={draft}
                isRunning={isRunning}
                dirty={dirty}
                isSaved={pipeline.id !== undefined}
                message={message || modelsError || ''}
                onDraftChange={setDraft}
                onRun={() => void startRun()}
              />
              {run && (
                <LiveRunHeader
                  run={run}
                  onStop={() => void latest.stop()}
                  onResume={() => void latest.resume()}
                  busy={latest.busy}
                  error={latest.error}
                  actions={
                    <Link
                      to={`/runs/${run.id}`}
                      className="rounded-lg border border-white/15 px-3 py-1.5 text-sm text-slate-200 transition-colors hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400"
                    >
                      Open in Runs
                    </Link>
                  }
                  note={
                    shown ? undefined : (
                      <p className="mt-2 text-xs text-slate-400">
                        This run used another version of the pipeline; open it in Runs to see its
                        steps.
                      </p>
                    )
                  }
                />
              )}
            </PipelineRunView>
          </div>
        </div>
      </main>
    </div>
  );
}
