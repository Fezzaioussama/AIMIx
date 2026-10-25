import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';

import type { MissionTemplate, Pipeline } from '../../core/api/types';
import { useMountedRef } from '../../core/hooks/useMountedRef';
import { missionPath } from '../../core/routes';
import { useFollowedRun } from '../runs/useFollowedRun';
import { adoptedState } from './missionAddress';
import { isRunRequest } from './missionIntent';
import { teamReply, you } from './missionMessages';
import type { StoredMission } from './missionStorage';
import { describeTeam } from './teamBrief';
import { useMissionConversation, type Conversation } from './useMissionConversation';
import { NO_TEAM, useMissionProposals } from './useMissionProposals';
import { useMissionRun } from './useMissionRun';
import { useMissionTeam, type MissionTeam } from './useMissionTeam';
import { useTeamGeneration } from './useTeamGeneration';

/** The builder opens a saved pipeline from router state `{ pipelineId }`. */
const BUILDER_PATH = '/pipeline';

/** Moves a new mission to its own address once its first save gives it an id. */
function useAdoptedAddress(
  routeId: number | undefined,
  savedId: number | undefined,
  leaving: { readonly current: boolean },
) {
  const navigate = useNavigate();
  useEffect(() => {
    if (routeId !== undefined || savedId === undefined || leaving.current) return;
    navigate(missionPath(savedId), { replace: true, state: adoptedState(savedId) });
  }, [leaving, navigate, routeId, savedId]);
}

/** A saved mission opened without a conversation in this tab starts with its team. */
function useReopenedGreeting(reopened: boolean, team: MissionTeam, conversation: Conversation) {
  const greeted = useRef(false);
  const { pipeline } = team;
  const { append } = conversation;
  const silent = conversation.messages.length === 0;
  useEffect(() => {
    if (greeted.current || !reopened || !silent || pipeline === null) return;
    greeted.current = true;
    append(teamReply(describeTeam(pipeline), 'reopened'));
  }, [append, pipeline, reopened, silent]);
}

/** Saves the mission when needed, then opens it in the builder (the advanced mode). */
function useOpenInBuilder(team: MissionTeam, leaving: { current: boolean }) {
  const navigate = useNavigate();
  const mounted = useMountedRef();
  return async () => {
    leaving.current = true;
    const saved = await team.save();
    leaving.current = saved.pipeline !== null && mounted.current;
    if (leaving.current && saved.pipeline?.id !== undefined) {
      navigate(BUILDER_PATH, { state: { pipelineId: saved.pipeline.id } });
    }
  };
}

/** The workspace's parts: the team, its conversation, newest run, planner and run form. */
function useMissionParts(routeId: number | undefined, seed: StoredMission) {
  const team = useMissionTeam(routeId, seed.draft);
  const savedId = team.pipeline?.id;
  const draft = savedId === undefined ? team.pipeline : null;
  const conversation = useMissionConversation(savedId ?? routeId, seed.messages, draft);
  const followed = useFollowedRun(team.pipeline ?? NO_TEAM, team.dirty);
  const generation = useTeamGeneration();
  const proposals = useMissionProposals(team, conversation);
  const run = useMissionRun(team, conversation, followed, proposals.settle);
  return { team, conversation, followed, generation, proposals, run };
}

/**
 * The mission workspace's state: the team, the conversation about it, its proposals
 * and its runs. What the person sends is routed here: the first message describes the
 * mission (a team is generated), "run it" asks for the run's inputs, and anything
 * else is a change request.
 */
export function useMission(routeId: number | undefined, seed: StoredMission) {
  const parts = useMissionParts(routeId, seed);
  const { team, conversation, generation, proposals, run } = parts;
  const leaving = useRef(false);
  useAdoptedAddress(routeId, team.pipeline?.id, leaving);
  useReopenedGreeting(routeId !== undefined, team, conversation);
  const openInBuilder = useOpenInBuilder(team, leaving);

  const thinking = generation.generating || proposals.revision.busy;
  // A saved mission that is loading, or could not be loaded, cannot be talked to yet.
  const unavailable = team.status === 'loading' || (routeId !== undefined && !team.pipeline);

  async function describe(description: string) {
    conversation.append(you(description));
    const outcome = await generation.generate(description);
    if (outcome === null) return;
    if (outcome.team) team.adopt(outcome.team);
    conversation.append(outcome.reply);
  }

  /** Routes what the person typed; false when nothing can be sent right now. */
  function send(text: string): boolean {
    const said = text.trim();
    if (!said || thinking || unavailable) return false;
    if (team.pipeline === null) void describe(said);
    else if (isRunRequest(said)) run.ask(said);
    else proposals.request(said);
    return true;
  }

  function startFromTemplate(template: MissionTemplate, created: Pipeline) {
    team.adopt(created);
    const reply = teamReply(describeTeam(created), 'template');
    conversation.append(you(`Start from the “${template.title}” template`), reply);
  }

  return { ...parts, thinking, unavailable, send, startFromTemplate, openInBuilder };
}

export type Mission = ReturnType<typeof useMission>;
