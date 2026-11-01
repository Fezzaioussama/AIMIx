import { useCallback, useEffect, useRef, type ReactNode, type RefObject } from 'react';
import { Link } from 'react-router-dom';

import type { Run, RunStatus } from '../../../core/api/types';
import { FOCUS_RING } from '../../../core/ui/focus';
import { Heading } from '../../../core/ui/Heading';
import { SwapText } from '../../../core/ui/SwapText';
import type { RunControls } from '../useRun';
import { ActionRow } from './ActionRow';
import { JumpLinks } from './JumpLinks';
import { MetaLine } from './MetaLine';
import { OUTCOME_COPY, settingsHint, type OutcomeWords } from './outcomeCopy';
import { ProgressRule } from './ProgressRule';
import { reportIds, type ReportModel } from './reportModel';
import { GivenLine } from './RunGiven';
import { SignOff } from './SignOff';

/**
 * Stop and Resume take away the button that was pressed. Once the run has answered,
 * the keyboard lands on the outcome heading instead of the top of the page; focus that
 * has gone somewhere else meanwhile is left alone.
 */
function useFocusAfterAction(
  heading: RefObject<HTMLHeadingElement | null>,
  busy: boolean,
  status: RunStatus,
): () => void {
  const pending = useRef(false);
  useEffect(() => {
    if (busy || !pending.current) return;
    pending.current = false;
    const focused = document.activeElement;
    if (focused === null || focused === document.body) heading.current?.focus();
  }, [heading, busy, status]);
  return useCallback(() => {
    pending.current = true;
  }, []);
}

/** The outcome in one plain sentence, then a quieter line or the way to fix the setup. */
function OutcomeSentence({ run, words }: { run: Run; words: OutcomeWords }) {
  const hint = settingsHint(run);
  return (
    <>
      <p className="mt-2 text-base text-pretty text-slate-300">{words.sentence}</p>
      {words.aside && <p className="mt-1 text-sm text-pretty text-slate-400">{words.aside}</p>}
      {hint !== null && (
        <p className="mt-2 text-sm text-slate-300">
          {hint}{' '}
          <Link
            to="/settings"
            className={`rounded-sm font-medium text-sky-300 underline underline-offset-4 hover:text-sky-200 ${FOCUS_RING}`}
          >
            Open Settings
          </Link>
        </p>
      )}
    </>
  );
}

interface OutcomeHeaderProps {
  run: Run;
  model: ReportModel;
  control: RunControls;
  level: 2 | 3;
  /** The screen's own controls after the run's action, e.g. Delete. */
  actions?: ReactNode;
  /** A quiet line before the rule, e.g. that the run used an earlier version. */
  note?: string;
  linkToRuns?: boolean;
  /** Whether the reviewer's full check is open; the report keeps it. */
  checkOpen: boolean;
  onToggleCheck: () => void;
}

/**
 * The top of a run's report: what happened and what to do now (the heading, one sentence,
 * the state's one action), whether to trust it (the sign-off), then the facts, closed by
 * the progress rule.
 */
export function OutcomeHeader(props: OutcomeHeaderProps) {
  const { run, model, control, level } = props;
  const words = OUTCOME_COPY[model.outcome]({ run, model });
  const heading = useRef<HTMLHeadingElement>(null);
  const focusAfter = useFocusAfterAction(heading, control.busy, run.status);
  return (
    <header>
      {/* Named by the current words: the old ones are still swapping out (M2) when Stop or
          Resume moves the focus here, and must not be read as the outcome. */}
      <Heading
        level={level}
        id={reportIds(run.id).outcome}
        ref={heading}
        tabIndex={-1}
        aria-label={words.heading}
        className={`rounded-sm text-xl font-semibold tracking-tight text-balance text-white sm:text-2xl ${FOCUS_RING}`}
      >
        <SwapText text={words.heading} />
      </Heading>
      <OutcomeSentence run={run} words={words} />
      <ActionRow
        run={run}
        control={control}
        onAct={focusAfter}
        outcome={model.outcome}
        actions={props.actions}
      />
      <SignOff
        run={run}
        reviewer={model.reviewer}
        level={level}
        open={props.checkOpen}
        onToggle={props.onToggleCheck}
      />
      <JumpLinks runId={run.id} deliverables={model.deliverables} />
      <MetaLine run={run} linkToRuns={props.linkToRuns} />
      <GivenLine run={run} />
      {props.note && <p className="mt-2 text-xs text-slate-400">{props.note}</p>}
      <ProgressRule outcome={model.outcome} done={model.done} total={model.total} />
    </header>
  );
}
