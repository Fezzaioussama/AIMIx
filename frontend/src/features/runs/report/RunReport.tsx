import { useMemo, useState, type ReactNode } from 'react';

import type { Run } from '../../../core/api/types';
import { Announcer } from '../../../core/ui/Announcer';
import { PendingApprovals } from '../PendingApprovals';
import type { RunControls } from '../useRun';
import { DeliverableList } from './DeliverableList';
import { FeedbackRow } from './FeedbackRow';
import { useJump } from './jump';
import { OutcomeHeader } from './OutcomeHeader';
import { reportIds, reportModel, type ReportModel } from './reportModel';
import { RunFiles } from './RunFiles';
import { signOffIds } from './SignOff';
import { TeamWork } from './TeamWork';
import { useRunAnnouncements } from './useRunAnnouncements';

/** What the screen showing the report adds to it. */
export interface ReportExtras {
  /** "Open in Runs" in the meta line, away from the Runs page. */
  linkToRuns?: boolean;
  /** Controls after the run's own action, e.g. Delete. */
  actions?: ReactNode;
  /** A quiet line in the header, e.g. that the run used an earlier version. */
  note?: string;
  /** The team's diagram in "How your team got there", where it is not on screen already. */
  diagram?: boolean;
}

interface ReportBodyProps {
  run: Run;
  model: ReportModel;
  control: RunControls;
  level: 2 | 3;
  diagram: boolean;
  onReadCheck: () => void;
}

/**
 * Under the header: the deliverables, your feedback once the run ended, the files saved
 * meanwhile, how the team got there.
 */
function ReportBody({ run, model, control, level, diagram, onReadCheck }: ReportBodyProps) {
  const [teamOpen, setTeamOpen] = useState(false);
  return (
    <>
      {/* A section with nothing to say renders nothing, and its spacing goes with it. */}
      <div className="mt-10 empty:hidden">
        <DeliverableList run={run} model={model} level={level} />
      </div>
      <div className="mt-10 empty:hidden">
        <FeedbackRow run={run} control={control} level={level} />
      </div>
      <div className="mt-14 empty:hidden">
        <RunFiles run={run} level={level} />
      </div>
      <div className="mt-14">
        <TeamWork
          run={run}
          model={model}
          level={level}
          open={teamOpen}
          onToggle={() => setTeamOpen((open) => !open)}
          diagram={diagram}
          onReadCheck={onReadCheck}
        />
      </div>
    </>
  );
}

interface RunReportProps {
  run: Run;
  control: RunControls;
  /** The level of the report's headings: 3 under a pane or page h2, 2 under the h1. */
  level: 2 | 3;
  extras?: ReportExtras;
}

/**
 * One run as one document its team hands over (brief §1): what happened and what to do
 * now, whether to trust it, the deliverables, the files saved meanwhile, and how the team
 * got there. The same on a mission, on the Runs page and in the builder; render it with
 * `key={run.id}`, so each run starts with its panels closed and nothing to announce.
 */
export function RunReport({ run, control, level, extras = {} }: RunReportProps) {
  const model = useMemo(() => reportModel(run), [run]);
  const [checkOpen, setCheckOpen] = useState(false);
  const message = useRunAnnouncements(run, model);
  const jump = useJump();
  const ids = reportIds(run.id);

  function readCheck() {
    setCheckOpen(true);
    jump(ids.signOff, signOffIds(run.id).toggle);
  }

  return (
    <article aria-labelledby={ids.outcome} className="w-full max-w-[36rem]">
      <OutcomeHeader
        run={run}
        model={model}
        control={control}
        level={level}
        actions={extras.actions}
        note={extras.note}
        linkToRuns={extras.linkToRuns}
        checkOpen={checkOpen}
        onToggleCheck={() => setCheckOpen((open) => !open)}
      />
      <PendingApprovals
        run={run}
        onApprove={(approvalId) => void control.approve(approvalId)}
        onDecline={(approvalId) => void control.decline(approvalId)}
        onAnswer={(approvalId, text) => void control.answer(approvalId, text)}
        busy={control.busy}
      />
      <ReportBody
        run={run}
        model={model}
        control={control}
        level={level}
        diagram={extras.diagram ?? false}
        onReadCheck={readCheck}
      />
      <Announcer message={message} />
    </article>
  );
}
