import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';

import type { MissionTemplate, Pipeline, PlanAnswer } from '../../core/api/types';
import { useMountedRef } from '../../core/hooks/useMountedRef';
import { missionPath } from '../../core/routes';
import { useFollowedRun } from '../runs/useFollowedRun';
import { adoptedState } from './missionAddress';
import { isRunRequest } from './missionIntent';
import {
  openQuestions,
  settleQuestions,
  teamReply,
  you,
  type QuestionsMessage,
} from './missionMessages';
import type { StoredMission } from './missionStorage';
import { describeTeam } from './teamBrief';
import { useMissionConversation, type Conversation } from './useMissionConversation';
import { NO_TEAM, useMissionProposals } from './useMissionProposals';
import { useMissionRun } from './useMissionRun';
import { useMissionTeam, type MissionTeam } from './useMissionTeam';
import { useTeamGeneration, type Briefing } from './useTeamGeneration';

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

type MissionParts = ReturnType<typeof useMissionParts>;

/** Planning the team: from the description, or from the answers to the planner's questions. */
function useMissionPlanning({ team, conversation, generation }: MissionParts, thinking: boolean) {
  async function plan(description: string, briefing?: Briefing) {
    const outcome = await generation.generate(description, briefing);
    if (outcome === null) return;
    if (outcome.team) team.adopt(outcome.team);
    conversation.append(outcome.reply);
  }

  /**
   * Answers the planner's questions, said in words as `said`, and plans with the
   * answers; no answers skips the questions. Either way it asks nothing more.
   */
  function answer(asked: QuestionsMessage, answers: PlanAnswer[], said: string) {
    if (thinking || openQuestions(conversation.messages)?.id !== asked.id) return;
    conversation.update(asked.id, settleQuestions(answers.length ? 'answered' : 'skipped'));
    conversation.append(you(said));
    void plan(asked.description, { answers, mayAsk: false });
  }

  return { plan, answer };
}

/** A message typed while the planner's questions are open answers all of them at once. */
function typedAnswer(asked: QuestionsMessage, text: string): PlanAnswer {
  return { question: asked.questions.map((item) => item.question).join('\n'), answer: text };
}

/**
 * The mission workspace's state: the team, the conversation about it, its proposals
 * and its runs. What the person sends is routed here: the first message describes the
 * mission (a team is generated, or the planner asks questions first, which the next
 * message answers), "run it" asks for the run's inputs, and anything else is a change
 * request.
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

  const { plan, answer } = useMissionPlanning(parts, thinking);

  /** Routes what the person typed; false when nothing can be sent right now. */
  function send(text: string): boolean {
    const said = text.trim();
    if (!said || thinking || unavailable) return false;
    const asked = openQuestions(conversation.messages);
    if (asked) answer(asked, [typedAnswer(asked, said)], said);
    else if (team.pipeline === null) {
      conversation.append(you(said));
      void plan(said);
    } else if (isRunRequest(said)) run.ask(said);
    else proposals.request(said);
    return true;
  }

  function startFromTemplate(template: MissionTemplate, created: Pipeline) {
    team.adopt(created);
    const reply = teamReply(describeTeam(created), 'template');
    conversation.append(you(`Start from the “${template.title}” template`), reply);
  }

  return { ...parts, thinking, unavailable, send, answer, startFromTemplate, openInBuilder };
}

export type Mission = ReturnType<typeof useMission>;
