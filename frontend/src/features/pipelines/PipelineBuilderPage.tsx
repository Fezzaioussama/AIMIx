import { useState } from 'react';
import { useLocation } from 'react-router-dom';

import type { Pipeline } from '../../core/api/types';
import { useModels } from '../../core/hooks/useModels';
import { useAgentTools } from '../../core/hooks/useAgentTools';
import { BusyNotice } from '../../core/ui/BusyNotice';
import { CountUp } from '../../core/ui/reactbits/CountUp';
import { ShinyText } from '../../core/ui/reactbits/ShinyText';
import { RunReport } from '../runs/report/RunReport';
import { useFollowedRun, type FollowedRun } from '../runs/useFollowedRun';
import { SchedulePanel } from '../schedules/SchedulePanel';
import { OpenInMissionLink } from './OpenInMissionLink';
import { PipelineGraph } from './PipelineGraph';
import { PipelineInputsEditor } from './PipelineInputsEditor';
import { RecentPipelines } from './RecentPipelines';
import { RevisePanel } from './RevisePanel';
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
  const followed = useFollowedRun(pipeline, dirty);

  const isSaving = status === 'saving';
  const isStarting = status === 'running';
  const isRunning = isStarting || followed.active;

  function editStep(order: number) {
    document.getElementById(`step-editor-${order}`)?.scrollIntoView?.({ behavior: 'smooth' });
  }

  async function startRun() {
    const started = await actions.run(draft);
    if (started) followed.follow(started);
  }

  // The editor sits beside the canvas only from `xl`: below it the app sidebar leaves the
  // canvas too little room, so the editor stacks above it and the window scrolls the page.
  // `<main>` scrolls only from `xl`: a scroll container that never scrolls would hold the
  // report's sticky title rows in place. Its vertical padding sits on the column inside it:
  // a sticky row stops below its scroller's top padding.
  return (
    <div className="flex min-h-[calc(100vh-60px)] flex-col text-slate-50 lg:min-h-dvh xl:h-dvh xl:flex-row">
      <aside
        inert={isStarting || isSaving}
        className="flex max-h-[45vh] w-full shrink-0 flex-col overflow-y-auto border-b border-white/10 bg-slate-950/60 p-6 backdrop-blur-xl xl:max-h-none xl:w-[350px] xl:border-r xl:border-b-0"
      >
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

      <main className="min-w-0 flex-1 px-4 sm:px-8 xl:overflow-y-auto 2xl:px-12">
        <div className="mx-auto max-w-6xl py-4 sm:py-8 2xl:py-12">
          <div className="mb-8">
            <CanvasHeader pipeline={pipeline} dirty={dirty} />
            <RevisePanel
              pipeline={pipeline}
              onApply={actions.replace}
              disabled={isRunning || isSaving}
              className="mb-6"
            />
            <SchedulePanel pipeline={pipeline} dirty={dirty} className="mb-6" />
            {/* The diagram shows the latest run only when it ran exactly this version. */}
            <PipelineGraph
              steps={pipeline.steps}
              inputs={pipeline.inputs}
              liveSteps={followed.shown?.steps}
              isRunning={followed.shown ? followed.shownActive : isStarting}
              input={draft.text}
              onEditStep={isRunning || isSaving ? undefined : editStep}
              onAddParallel={isRunning || isSaving ? undefined : actions.addParallelStep}
              onAddAfter={isRunning || isSaving ? undefined : actions.addStepAfter}
            />
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
            <LatestRun followed={followed} starting={isStarting} />
          </div>
        </div>
      </main>
    </div>
  );
}

/** The canvas's title: the pipeline's name, the way to its mission, and its size. */
function CanvasHeader({ pipeline, dirty }: { pipeline: Pipeline; dirty: boolean }) {
  const stageCount = new Set(pipeline.steps.map((step) => step.stage)).size;
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <p className="mb-1 text-xs font-semibold tracking-widest uppercase">
          <ShinyText className="text-sky-400/80">Workflow canvas</ShinyText>
        </p>
        <h1 className="text-2xl font-bold tracking-tight">{pipeline.name || 'New Pipeline'}</h1>
        <div className="mt-3">
          <OpenInMissionLink pipelineId={pipeline.id} dirty={dirty} />
        </div>
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
  );
}

/** The pipeline's newest run, handed over as its report; or word that one is starting. */
function LatestRun({ followed, starting }: { followed: FollowedRun; starting: boolean }) {
  const { run } = followed;
  if (run === null) {
    return starting ? <BusyNotice className="mt-8">Starting the run…</BusyNotice> : null;
  }
  return (
    // The window scrolls below xl, under the 60px top bar that sits there below lg.
    <section aria-label="Latest run" className="mt-10 [--sticky-top:60px] lg:[--sticky-top:0px]">
      <RunReport
        key={run.id}
        run={run}
        control={followed}
        level={2}
        extras={{
          linkToRuns: true,
          note: followed.shown ? undefined : 'This run used an earlier version of this pipeline.',
        }}
      />
    </section>
  );
}
