/**
 * A run as its report reads it (pure, no React): which steps are the deliverables and
 * where each is, which step checks the work, and the outcome the header tells. Everything
 * comes from the run itself — its steps and the definition it was started with — never
 * from the pipeline as it is now, which may have changed since.
 */
import type { PipelineStep, Run, RunStatus, RunStep, RunStepStatus } from '../../../core/api/types';
import { groupByStage, stepLabel } from '../../pipelines/stages';
import { BUDGET_ERROR_CODE } from '../runBudget';
import { isActive } from '../runStatus';
import { fixingRound, isSentBack, isSettled, loopRounds } from './reviewRounds';

/** Where a run is, as the report's outcome header tells it. */
export type OutcomeKind =
  | 'queued'
  | 'running'
  | 'checking'
  | 'fixing'
  | 'waiting'
  | 'done'
  | 'doneNothing'
  | 'limit'
  | 'failed'
  | 'stopped'
  | 'interrupted';

/** Where one deliverable is: a document to read, or a slot saying why it is not one yet. */
export type DeliverableState =
  'ready' | 'writing' | 'revising' | 'needsOk' | 'waiting' | 'queued' | 'notFinished' | 'skipped';

/** One deliverable of a run: its step, how the run's own definition describes it, and where it is. */
export interface DeliverableView {
  step: RunStep;
  definition: PipelineStep;
  title: string;
  /** The agent's role, trimmed; empty when the step has none. */
  role: string;
  state: DeliverableState;
}

/** The step that checks the work (VERDICT PASS/REVISE) and how the run's definition describes it. */
export interface ReviewerView {
  step: RunStep;
  definition: PipelineStep;
}

export interface ReportModel {
  /** In run order: by stage, then by order within a stage. */
  deliverables: DeliverableView[];
  /** Null without a reviewer, and when the reviewer is the only output (then it is a deliverable). */
  reviewer: ReviewerView | null;
  /** Steps done with: finished or skipped, and not sent back by a review to be done again. */
  done: number;
  total: number;
  outcome: OutcomeKind;
}

/** What Resume keeps, and where it starts again from, by step title. */
export interface KeptParts {
  kept: string[];
  from: string[];
}

/** The element ids a report's parts carry, so links and focus can find them. */
export interface ReportIds {
  outcome: string;
  signOff: string;
  deliverable: (order: number) => string;
  title: (order: number) => string;
  agent: (order: number) => string;
  /** "What the service said": the raw error behind a failure. */
  serviceSaid: string;
  /** "How your team got there". */
  team: string;
  /** "Saved during this run". */
  files: string;
}

export function reportIds(runId: number): ReportIds {
  const base = `run-${runId}`;
  return {
    outcome: `${base}-outcome`,
    signOff: `${base}-sign-off`,
    deliverable: (order) => `${base}-deliverable-${order}`,
    title: (order) => `${base}-deliverable-${order}-title`,
    agent: (order) => `${base}-agent-${order}`,
    serviceSaid: `${base}-service-said`,
    team: `${base}-team`,
    files: `${base}-files`,
  };
}

/** A step's name in the report: its title, or its position when it has none. */
export function titleOf(step: RunStep): string {
  return stepLabel({ order: step.step_order, title: step.title });
}

/** In the order the steps run: by stage, then by order within a stage. */
export function inRunOrder(steps: RunStep[]): RunStep[] {
  return [...steps].sort((a, b) => a.stage - b.stage || a.step_order - b.step_order);
}

/** How the run's definition describes the step; a step it lacks is read from its result row. */
export function definitionOf(run: Run, step: RunStep): PipelineStep {
  const defined = run.definition.steps.find((item) => item.order === step.step_order);
  return (
    defined ?? {
      order: step.step_order,
      stage: step.stage,
      title: step.title,
      is_output: step.is_output,
      expected_output: '',
      prompt: '',
      model: step.model,
      role: '',
      allowed_tools: [],
      condition: null,
      review: null,
    }
  );
}

/** Whether the step's agent asked to use a tool and waits for the person's answer. */
export function asksForOk(step: RunStep, run: Run): boolean {
  return run.pending_approvals.some((approval) => approval.step_order === step.step_order);
}

/** The step that checks the work: the last one, by stage, whose definition has a review. */
export function reviewerDefinition(steps: PipelineStep[]): PipelineStep | null {
  return steps
    .filter((step) => step.review !== null)
    .reduce<PipelineStep | null>(
      (found, step) => (found && found.stage > step.stage ? found : step),
      null,
    );
}

function reviewerStep(run: Run): RunStep | undefined {
  const last = reviewerDefinition(run.definition.steps);
  return last === null ? undefined : run.steps.find((step) => step.step_order === last.order);
}

/** The run's output steps in run order; the reviewer only when it is the only output. */
export function deliverablesOf(run: Run): RunStep[] {
  const outputs = inRunOrder(run.steps.filter((step) => step.is_output));
  const reviewer = reviewerStep(run);
  const others = outputs.filter((step) => step !== reviewer);
  return others.length > 0 ? others : outputs;
}

export function reviewerOf(run: Run): ReviewerView | null {
  const step = reviewerStep(run);
  // As the only output it is the deliverable, and nothing checks it.
  if (step === undefined || deliverablesOf(run).includes(step)) return null;
  return { step, definition: definitionOf(run, step) };
}

/** A step that has not started: queued with its run, on its way, or left when the run ended. */
const PENDING_STATE: Record<RunStatus, DeliverableState> = {
  queued: 'queued',
  running: 'waiting',
  waiting: 'waiting',
  succeeded: 'notFinished',
  failed: 'notFinished',
  cancelled: 'notFinished',
  interrupted: 'notFinished',
};

type StateRule = (step: RunStep, run: Run, sentBack: boolean) => DeliverableState;

/** Where a deliverable is, by its step's status (Strategy + Registry, AGENTS.md §7). */
const STATE_BY_STATUS: Record<RunStepStatus, StateRule> = {
  pending: (_step, run) => PENDING_STATE[run.status],
  running: (step) => (step.rounds > 1 ? 'revising' : 'writing'),
  succeeded: (_step, run, sentBack) => (sentBack && isActive(run.status) ? 'revising' : 'ready'),
  // Sent back, its condition is weighed again in the new round.
  skipped: (_step, run, sentBack) => (sentBack && isActive(run.status) ? 'waiting' : 'skipped'),
  failed: () => 'notFinished',
  cancelled: () => 'notFinished',
};

export function deliverableState(step: RunStep, run: Run): DeliverableState {
  if (asksForOk(step, run)) return 'needsOk';
  return STATE_BY_STATUS[step.status](step, run, isSentBack(step, loopRounds(run)));
}

function runningOutcome(run: Run, reviewer: ReviewerView | null): OutcomeKind {
  if (reviewer?.step.status === 'running') return 'checking';
  return fixingRound(run) === null ? 'running' : 'fixing';
}

type OutcomeRule = (run: Run, reviewer: ReviewerView | null) => OutcomeKind;

/** The outcome by the run's status (Strategy + Registry, AGENTS.md §7). */
const OUTCOME_BY_STATUS: Record<RunStatus, OutcomeRule> = {
  queued: () => 'queued',
  running: runningOutcome,
  waiting: () => 'waiting',
  succeeded: (run) =>
    deliverablesOf(run).some((step) => step.status === 'succeeded') ? 'done' : 'doneNothing',
  failed: (run) => (run.error?.code === BUDGET_ERROR_CODE ? 'limit' : 'failed'),
  cancelled: () => 'stopped',
  interrupted: () => 'interrupted',
};

export function outcomeOf(run: Run, reviewer: ReviewerView | null): OutcomeKind {
  return OUTCOME_BY_STATUS[run.status](run, reviewer);
}

/** The steps of each stage that are not done with, lowest stage first; empty stages left out. */
function openStages(steps: RunStep[], run: Run): RunStep[][] {
  const loops = loopRounds(run);
  return groupByStage(inRunOrder(steps), (step) => step.stage)
    .map((group) => group.items.filter((step) => !isSettled(step, loops)))
    .filter((items) => items.length > 0);
}

/** The titles a step waits for: the unfinished steps of the highest earlier stage that has any. */
export function waitsFor(step: RunStep, run: Run): string[] {
  const earlier = openStages(
    run.steps.filter((other) => other.stage < step.stage),
    run,
  );
  return (earlier.at(-1) ?? []).map(titleOf);
}

/** What Resume keeps (the finished work) and the steps it starts again from. */
export function keptParts(run: Run): KeptParts {
  const loops = loopRounds(run);
  const kept = inRunOrder(run.steps).filter(
    (step) => step.status === 'succeeded' && !isSentBack(step, loops),
  );
  return { kept: kept.map(titleOf), from: (openStages(run.steps, run)[0] ?? []).map(titleOf) };
}

export function runningTitles(run: Run): string[] {
  return inRunOrder(run.steps.filter((step) => step.status === 'running')).map(titleOf);
}

function viewOf(step: RunStep, run: Run): DeliverableView {
  const definition = definitionOf(run, step);
  return {
    step,
    definition,
    title: titleOf(step),
    role: definition.role.trim(),
    state: deliverableState(step, run),
  };
}

export function reportModel(run: Run): ReportModel {
  const loops = loopRounds(run);
  const reviewer = reviewerOf(run);
  return {
    deliverables: deliverablesOf(run).map((step) => viewOf(step, run)),
    reviewer,
    done: run.steps.filter((step) => isSettled(step, loops)).length,
    total: run.steps.length,
    outcome: outcomeOf(run, reviewer),
  };
}
