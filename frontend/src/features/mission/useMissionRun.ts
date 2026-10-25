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
  /** The form asked for during this visit: it takes focus as it appears (a restored one
   * does not, so opening the page never moves focus). */
  newFormId: string | null;
  /** "Run it": asks for the mission's inputs in the conversation. */
  ask: (said?: string) => void;
  /** Saves the team when needed, then starts a run with the form's values; whether it
   * started. */
  start: () => Promise<boolean>;
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

/** AIMIx's answer to "run it": the form for the inputs, unless it cannot run now. */
function askReply(hasTeam: boolean, runActive: boolean): AimixMessage {
  if (!hasTeam) return note(NO_TEAM_YET);
  return runActive ? note(STILL_RUNNING) : inputsRequest();
}

/** Saves the team when it needs saving, then starts a run of it. */
async function saveAndLaunch(team: MissionTeam, draft: RunDraft): Promise<Launch> {
  const saved = await team.save();
  return saved.pipeline ? launch(saved.pipeline, draft) : { run: null, error: saved.error };
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
  const [newFormId, setNewFormId] = useState<string | null>(null);
  const mounted = useMountedRef();
  const { messages, append, update } = conversation;
  const formId = openInputsId(messages);

  function ask(said = 'Run it') {
    settleProposal();
    if (formId !== null) update(formId, settleInputs('closed'));
    setError('');
    const reply = askReply(team.pipeline !== null, followed.active);
    append(you(said), reply);
    setNewFormId(reply.kind === 'inputs' ? reply.id : null);
  }

  async function start(): Promise<boolean> {
    const form = formId;
    if (form === null || starting) return false;
    setStarting(true);
    setError('');
    const outcome = await saveAndLaunch(team, draft);
    if (!mounted.current) return false;
    setStarting(false);
    if (outcome.run === null) {
      setError(outcome.error);
      return false;
    }
    followed.follow(outcome.run);
    update(form, settleInputs('started'));
    append(runReply(outcome.run.id));
    setDraft(EMPTY_RUN_DRAFT);
    return true;
  }

  return { draft, setDraft, starting, error, formId, newFormId, ask, start };
}
