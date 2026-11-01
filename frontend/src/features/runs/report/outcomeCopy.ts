/**
 * The words of a run report's outcome header: a heading and one plain sentence per outcome
 * (brief §7, word for word). Pure, so every screen that shows a run says the same thing.
 */
import type { Run, RunStep } from '../../../core/api/types';
import { elapsedMs, formatDuration } from '../../../core/time';
import { countOf } from '../../../core/usageFormat';
import { joinWords } from '../../pipelines/revision';
import { roundLabel } from '../../pipelines/roundNotes';
import { askedBy } from '../approvalFormat';
import { BUDGET_ERROR_CODE } from '../runBudget';
import { approvalAsk } from '../toolWords';
import {
  inRunOrder,
  keptParts,
  runningTitles,
  titleOf,
  type OutcomeKind,
  type ReportModel,
} from './reportModel';
import { fixingRound } from './reviewRounds';

/** What the outcome header's words are made from. */
export interface OutcomeFacts {
  run: Run;
  model: ReportModel;
}

/** The outcome header's words: a heading, one sentence, and an optional quiet line. */
export interface OutcomeWords {
  heading: string;
  sentence: string;
  aside?: string;
}

/** The error code of a run whose account has no AI service key (api/exceptions.py). */
const PROVIDER_NOT_CONFIGURED = 'provider_not_configured';

/** Why something stopped, by the error code the server recorded (api/exceptions.py). */
export const FAILURE_WORDS: Record<string, string> = {
  provider_timeout: 'the AI service did not answer in time',
  provider_unavailable: 'the AI service could not be reached',
  [PROVIDER_NOT_CONFIGURED]: 'no AI service is set up for your account',
  upstream_response_invalid: 'the AI service sent an answer that could not be used',
  tool_unavailable: 'a tool it needs is not available',
  server_error: 'something went wrong on our side',
  [BUDGET_ERROR_CODE]: 'the run reached its spending limit',
};

/** Finished agents up to this many are named in the resume sentence; more are counted. */
const NAMED_KEPT = 2;

/** Why it stopped, to follow "stopped because"; a code without words is "something went wrong". */
export function failureReason(code: string | null | undefined): string {
  return code && Object.hasOwn(FAILURE_WORDS, code) ? FAILURE_WORDS[code] : 'something went wrong';
}

/** What Resume would do: the work it keeps, and where it starts again. */
export function keptSentence(run: Run): string {
  const { kept, from } = keptParts(run);
  if (kept.length === 0)
    return 'Nothing was finished yet, so Resume starts again from the beginning.';
  const keeps =
    kept.length > NAMED_KEPT ? `the work of ${countOf(kept.length, 'agent')}` : joinWords(kept);
  const then = from.length > 0 ? `starts again from ${joinWords(from)}` : 'finishes the run';
  return `Resume keeps ${keeps} and ${then}.`;
}

/** What to do when the account has no AI service set up; null for any other failure. */
export function settingsHint(run: Run): string | null {
  return run.error?.code === PROVIDER_NOT_CONFIGURED
    ? 'Add an AI service key in Settings, then resume.'
    : null;
}

function agentsDone(model: ReportModel): string {
  return `${model.done} of ${countOf(model.total, 'agent')} done.`;
}

function running({ run, model }: OutcomeFacts): OutcomeWords {
  const working = runningTitles(run);
  const now =
    working.length > 0 ? `Now working: ${joinWords(working)}.` : 'Getting the next agent ready.';
  return {
    heading: 'Your team is working',
    sentence: `${now} ${agentsDone(model)}`,
    aside: 'Each deliverable appears below as soon as it is ready, even if you leave this page.',
  };
}

function fixing({ run }: OutcomeFacts): OutcomeWords {
  const at = fixingRound(run);
  const round = at === null ? '' : ` on ${roundLabel(at.round, at.total).toLowerCase()}`;
  return {
    heading: 'Fixing what the check found',
    sentence: `Your team is working${round}. Each deliverable appears below again as soon as it is ready.`,
  };
}

function waiting({ run }: OutcomeFacts): OutcomeWords {
  const asks = run.pending_approvals;
  const sentence =
    asks.length === 1
      ? `${askedBy(run, asks[0].step_order)} wants to ${approvalAsk(asks[0])}. The run waits until you answer below.`
      : `${asks.length} requests are waiting for your answer below.`;
  return { heading: 'Your team needs your OK', sentence };
}

/** " A was skipped because …", for the deliverables whose condition was not met. */
function skippedSentence(model: ReportModel): string {
  const skipped = model.deliverables.filter((view) => view.state === 'skipped');
  if (skipped.length === 0) return '';
  if (skipped.length === 1)
    return ` ${skipped[0].title} was skipped because its condition was not met.`;
  const names = joinWords(skipped.map((view) => view.title));
  return ` ${names} were skipped because their condition was not met.`;
}

function done({ run, model }: OutcomeFacts): OutcomeWords {
  const ready = model.deliverables.filter((view) => view.state === 'ready').length;
  const took = elapsedMs(run.started_at, run.finished_at, Date.now());
  return {
    heading: `${countOf(ready, 'deliverable')} ready`,
    sentence: `${took === null ? 'Done.' : `Done in ${formatDuration(took)}.`}${skippedSentence(model)}`,
  };
}

/** The step that stopped the run: the first failed one with an error, else the first failed. */
function failedStep(run: Run): RunStep | undefined {
  const failed = inRunOrder(run.steps).filter((step) => step.status === 'failed');
  return failed.find((step) => step.error !== null) ?? failed[0];
}

function failed({ run }: OutcomeFacts): OutcomeWords {
  const step = failedStep(run);
  const who = step === undefined ? 'It' : titleOf(step);
  return {
    heading: 'The run stopped before it finished',
    sentence: `${who} stopped because ${failureReason(run.error?.code)}. ${keptSentence(run)}`,
  };
}

function limit({ run }: OutcomeFacts): OutcomeWords {
  const parts = [
    run.error?.detail.trim() ?? '',
    'Raise the limit below to go on.',
    keptSentence(run),
  ];
  return {
    heading: 'The run stopped at its spending limit',
    sentence: parts.filter((part) => part !== '').join(' '),
  };
}

/** The header's words for each outcome (Strategy + Registry, AGENTS.md §7). */
export const OUTCOME_COPY: Record<OutcomeKind, (facts: OutcomeFacts) => OutcomeWords> = {
  queued: () => ({
    heading: 'Your team is lined up',
    sentence: 'It starts as soon as a slot is free.',
  }),
  running,
  checking: () => ({
    heading: 'Your work is being checked',
    sentence: 'You can read your deliverables below while the check runs.',
  }),
  fixing,
  waiting,
  done,
  doneNothing: () => ({
    heading: 'Done, with no deliverable',
    sentence:
      'The agents that make the deliverables were skipped because their condition was not met.',
  }),
  limit,
  failed,
  stopped: ({ run }) => ({ heading: 'You stopped the run', sentence: keptSentence(run) }),
  interrupted: ({ run }) => ({
    heading: 'The run was interrupted',
    sentence: `The server restarted while your team was working. ${keptSentence(run)}`,
  }),
};
