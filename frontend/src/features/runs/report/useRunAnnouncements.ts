/**
 * What a run report says aloud while you are on it (brief §6): one polite line for each
 * change worth hearing between two polls, never for the run as it first loads. A change of
 * status wins, then a reviewer asking for fixes, then deliverables that became ready.
 */
import { useState } from 'react';

import type { Run, RunApproval, RunStatus } from '../../../core/api/types';
import { countOf } from '../../../core/usageFormat';
import { joinWords } from '../../pipelines/revision';
import { roundLabel } from '../../pipelines/roundNotes';
import { askedBy } from '../approvalFormat';
import { isResumable } from '../runStatus';
import { approvalAsk } from '../toolWords';
import { OUTCOME_COPY, type OutcomeFacts } from './outcomeCopy';
import type { DeliverableView, OutcomeKind, ReportModel } from './reportModel';
import { fixingRound } from './reviewRounds';
import { reviewerName, reviewerNameAtStart, signOff } from './signOffCopy';

/** Added to (or dropped from) a line the same as the last one, so it is heard again. */
const REPEAT = ' ';

function isReady(view: DeliverableView): boolean {
  return view.state === 'ready';
}

/** "Your team finished: 2 deliverables ready, approved by the Orchestrator." */
function finished({ run, model }: OutcomeFacts): string {
  const ready = model.deliverables.filter(isReady).length;
  if (ready === 0) return 'Your team finished, with no deliverable.';
  const approved =
    model.reviewer !== null && signOff(model.reviewer, run)?.tone === 'approved'
      ? `, approved by ${reviewerName(model.reviewer.definition)}`
      : '';
  return `Your team finished: ${countOf(ready, 'deliverable')} ready${approved}.`;
}

/** "Draft wants to use “Send email” from crm", or "Draft has a question for you". */
function askWords(run: Run, ask: RunApproval): string {
  const who = askedBy(run, ask.step_order);
  return ask.kind === 'question'
    ? `${who} has a question for you`
    : `${who} wants to ${approvalAsk(ask)}`;
}

/** "Your team needs your OK: Draft wants to use “Send email” from crm." */
function needsOk({ run }: OutcomeFacts): string {
  const asks = run.pending_approvals;
  if (asks.length === 0) return 'Your team needs your OK.';
  const what =
    asks.length === 1
      ? askWords(run, asks[0])
      : `${asks.length} requests are waiting for your answer`;
  return `Your team needs your OK: ${what}.`;
}

/** The outcome's own heading, as a sentence: "You stopped the run." */
function headingLine(facts: OutcomeFacts): string {
  return `${OUTCOME_COPY[facts.model.outcome](facts).heading}.`;
}

/** What a run that has just changed status into each outcome says (Strategy + Registry). */
const ON_ARRIVAL: Partial<Record<OutcomeKind, (facts: OutcomeFacts) => string>> = {
  done: finished,
  doneNothing: finished,
  waiting: needsOk,
  limit: headingLine,
  failed: headingLine,
  stopped: headingLine,
  interrupted: headingLine,
};

type Line = (previous: OutcomeFacts, next: OutcomeFacts) => string;

/** A run that goes on again: resumed, or past the request you just answered. */
function goesOnAgain(previous: RunStatus): boolean {
  return isResumable(previous) || previous === 'waiting';
}

const statusLine: Line = (previous, next) => {
  if (previous.run.status === next.run.status) return '';
  const say = ON_ARRIVAL[next.model.outcome];
  if (say !== undefined) return say(next);
  return goesOnAgain(previous.run.status) ? 'Your team is working again.' : '';
};

/** "The Orchestrator asked for fixes. Round 2 of 3 has started." when it has just asked. */
const fixesLine: Line = (previous, next) => {
  const { reviewer } = next.model;
  const now = signOff(reviewer, next.run);
  if (reviewer === null || now?.tone !== 'fixes') return '';
  if (signOff(previous.model.reviewer, previous.run)?.key === now.key) return '';
  const at = fixingRound(next.run);
  const round = at === null ? '' : ` ${roundLabel(at.round, at.total)} has started.`;
  return `${reviewerNameAtStart(reviewer.definition)} asked for fixes.${round}`;
};

/** "Draft and Summary ready." for the deliverables that have just become documents. */
const readyLine: Line = (previous, next) => {
  const before = new Set(
    previous.model.deliverables.filter(isReady).map((view) => view.step.step_order),
  );
  const fresh = next.model.deliverables.filter(
    (view) => isReady(view) && !before.has(view.step.step_order),
  );
  return fresh.length === 0 ? '' : `${joinWords(fresh.map((view) => view.title))} ready.`;
};

/** In the order they win when several changes come in one poll. */
const LINES: Line[] = [statusLine, fixesLine, readyLine];

/** What to say about the change from `previous` to `next`; '' when nothing worth saying. */
export function announcementFor(previous: OutcomeFacts, next: OutcomeFacts): string {
  for (const line of LINES) {
    const said = line(previous, next);
    if (said !== '') return said;
  }
  return '';
}

/** `line`, made to differ from the last message so a live region speaks it again. */
function spoken(line: string, last: string): string {
  return line === last ? `${line}${REPEAT}` : line;
}

interface Heard {
  facts: OutcomeFacts;
  message: string;
}

/**
 * The message for the report's `Announcer`: '' as the run first shows, then the line for
 * each change worth hearing; the last one stays until a newer one replaces it.
 */
export function useRunAnnouncements(run: Run, model: ReportModel): string {
  const [heard, setHeard] = useState<Heard>({ facts: { run, model }, message: '' });
  // A new poll: compare it with the last one while rendering (no effect, no extra paint).
  if (heard.facts.run !== run) {
    const next = { run, model };
    const line = announcementFor(heard.facts, next);
    setHeard({ facts: next, message: line === '' ? heard.message : spoken(line, heard.message) });
  }
  return heard.message;
}
