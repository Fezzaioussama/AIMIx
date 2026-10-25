import { useState } from 'react';

import { errorMessage } from '../../core/api/errorMessage';
import { startRun } from '../../core/api/runs';
import type { Pipeline, Run } from '../../core/api/types';
import { useMountedRef } from '../../core/hooks/useMountedRef';
import { EMPTY_RUN_DRAFT, runRequest, type RunDraft } from '../pipelines/pipelineInputs';
import type { FollowedRun } from '../runs/useFollowedRun';
import {
  inputsRequest,
  note,
  openInputsId,
  runReply,
  settleInputs,
  you,
  type AimixMessage,
} from './missionMessages';
import type { Conversation } from './useMissionConversation';
import type { MissionTeam } from './useMissionTeam';

export const NO_TEAM_YET =
  'Describe your mission first, or pick a template, and I will put a team together.';
export const STILL_RUNNING =
  'Your team is still working on the last run. Follow it under Results, or stop it there first.';

export interface MissionRun {
  draft: RunDraft;
  setDraft: (draft: RunDraft) => void;
  /** The team is being saved and the run started. */
  starting: boolean;
  /** Why the last start failed; empty when it did not. */
  error: string;
  /** The run form the person can fill in, if one is open. */
  formId: string | null;
  /** "Run it": asks for the mission's inputs in the conversation. */
  ask: (said?: string) => void;
  /** Saves the team when needed, then starts a run with the form's values. */
  start: () => Promise<void>;
}

type Launch = { run: Run; error: '' } | { run: null; error: string };

async function launch(pipeline: Pipeline, draft: RunDraft): Promise<Launch> {
  if (pipeline.id === undefined) return { run: null, error: 'Save the mission before running it.' };
  try {
    return { run: await startRun(pipeline.id, runRequest(pipeline.inputs, draft)), error: '' };
  } catch (cause) {
    return { run: null, error: errorMessage(cause, 'The run could not start.') };
  }
}

/**
 * Running the mission from the conversation: "Run it" asks for the inputs in a form
 * there; starting saves the team first (a new mission is saved on its first run, edits
 * before each run), then starts a background run and follows it (`followed`).
 */
export function useMissionRun(
  team: MissionTeam,
  conversation: Conversation,
  followed: FollowedRun,
  settleProposal: () => void,
): MissionRun {
  const [draft, setDraft] = useState<RunDraft>(EMPTY_RUN_DRAFT);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState('');
  const mounted = useMountedRef();
  const { messages, append, update } = conversation;
  const formId = openInputsId(messages);

  function answer(): AimixMessage {
    if (team.pipeline === null) return note(NO_TEAM_YET);
    return followed.active ? note(STILL_RUNNING) : inputsRequest();
  }

  function ask(said = 'Run it') {
    settleProposal();
    if (formId !== null) update(formId, settleInputs('closed'));
    setError('');
    append(you(said), answer());
  }

  async function saveAndLaunch(): Promise<Launch> {
    const saved = await team.save();
    return saved.pipeline ? launch(saved.pipeline, draft) : { run: null, error: saved.error };
  }

  async function start() {
    const form = formId;
    if (form === null || starting) return;
    setStarting(true);
    setError('');
    const outcome = await saveAndLaunch();
    if (!mounted.current) return;
    setStarting(false);
    if (outcome.run === null) {
      setError(outcome.error);
      return;
    }
    followed.follow(outcome.run);
    update(form, settleInputs('started'));
    append(runReply(outcome.run.id));
    setDraft(EMPTY_RUN_DRAFT);
  }

  return { draft, setDraft, starting, error, formId, ask, start };
}
