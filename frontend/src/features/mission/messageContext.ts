import type { Pipeline, PlanAnswer, Run } from '../../core/api/types';
import type { AimixMessage, QuestionsMessage } from './missionMessages';
import type { PaneId } from './missionPanes';
import type { MissionProposals } from './useMissionProposals';
import type { MissionRun } from './useMissionRun';

/** What an answer needs from the workspace to be drawn live: its proposal, form or run. */
export interface MessageContext {
  team: Pipeline | null;
  proposals: MissionProposals;
  run: MissionRun;
  /** The mission's newest run, as last fetched. */
  latestRun: Run | null;
  /** A run of the mission is queued or running. */
  runActive: boolean;
  /** Brings a pane forward (its tab on a phone) and moves focus to it. */
  showPane: (pane: PaneId) => void;
  /** Gives the message box focus back, e.g. once a proposal is applied. */
  focusComposer: () => void;
  /** The planner's questions that can still be answered (the newest message), if any. */
  openQuestionsId: string | null;
  /** Answers them, said in words as `said`; no answers skips them. Then the team is planned. */
  answerQuestions: (asked: QuestionsMessage, answers: PlanAnswer[], said: string) => void;
  /** A document of the message box still being read, which planning waits for; '' if none. */
  planWaitsFor: string;
  /** One the open run form will get, which its run waits for; '' if none. */
  runWaitsFor: string;
  /** The open run form needs the documents again: AIMIx keeps only their names. */
  documentsGone: boolean;
}

/** The props of the view that draws one kind of answer. */
export interface ViewProps<K extends AimixMessage['kind']> {
  message: Extract<AimixMessage, { kind: K }>;
  context: MessageContext;
}
