import type { Pipeline, Run } from '../../core/api/types';
import type { AimixMessage } from './missionMessages';
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
}

/** The props of the view that draws one kind of answer. */
export interface ViewProps<K extends AimixMessage['kind']> {
  message: Extract<AimixMessage, { kind: K }>;
  context: MessageContext;
}
