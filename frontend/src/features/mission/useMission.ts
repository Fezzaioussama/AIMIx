import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';

import { DOCUMENTS_INPUT_NAME } from '../../core/api/pipelines';
import type { MissionTemplate, Pipeline, PlanAnswer } from '../../core/api/types';
import { useMountedRef } from '../../core/hooks/useMountedRef';
import { missionPath } from '../../core/routes';
import { sourceLabel } from '../pipelines/webLinks';
import { useFollowedRun } from '../runs/useFollowedRun';
import { adoptedState } from './missionAddress';
import {
  documentsTarget,
  noteOf,
  planDocumentOf,
  type DocumentPlacement,
} from './missionDocuments';
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
import { useMissionDocuments } from './useMissionDocuments';
import { NO_TEAM, useMissionProposals } from './useMissionProposals';
import { useMissionRun } from './useMissionRun';
import { useMissionTeam, type MissionTeam } from './useMissionTeam';
import { FIRST_ASK, useTeamGeneration, type Briefing } from './useTeamGeneration';

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

/**
 * The workspace's parts: the team, its conversation, newest run, planner, run form and
 * the documents added in the message box (one read while the form is open goes into it).
 */
function useMissionParts(routeId: number | undefined, seed: StoredMission) {
  const team = useMissionTeam(routeId, seed.draft);
  const savedId = team.pipeline?.id;
  const draft = savedId === undefined ? team.pipeline : null;
  const conversation = useMissionConversation(savedId ?? routeId, seed.messages, draft);
  const followed = useFollowedRun(team.pipeline ?? NO_TEAM, team.dirty);
  const generation = useTeamGeneration();
  const proposals = useMissionProposals(team, conversation);
  const run = useMissionRun(team, conversation, followed, proposals.settle);
  const documents = useMissionDocuments((document) => run.place([document]).length > 0);
  return { team, conversation, followed, generation, proposals, run, documents };
}

type MissionParts = ReturnType<typeof useMissionParts>;

/**
 * The box's documents as the open run form sees them: the one it waits for (one being read
 * that it will get), the ones it did not take (`placement`), and whether it needs the
 * documents again (they are kept by name only, so a new run or a reload has none).
 */
function documentsForRun({ team, run, documents }: MissionParts) {
  const inputs = team.pipeline?.inputs ?? [];
  const target = documentsTarget(inputs);
  const formOpen = run.formId !== null;
  const placement: DocumentPlacement | null =
    formOpen && documents.read.length > 0
      ? {
          names: documents.read.map((document) => sourceLabel(document.filename)),
          choices: target === null ? inputs : [],
          place: (input) => documents.release(run.place(documents.read, input)),
        }
      : null;
  const documentsGone =
    formOpen &&
    target === DOCUMENTS_INPUT_NAME &&
    (run.draft.values[target] ?? '').trim() === '' &&
    documents.items.every((item) => item.state === 'failed');
  return { runWaitsFor: target === null ? '' : documents.reading, placement, documentsGone };
}

/**
 * Planning the team: from the description, or from the answers to the planner's
 * questions. The documents read so far go with it (the planner reads the start of each)
 * and are named on the person's message; while one is still being read, planning waits
 * (`busy`) rather than leave it out.
 */
function useMissionPlanning(parts: MissionParts, busy: boolean) {
  const { team, conversation, generation, documents } = parts;

  async function plan(said: string, description: string, briefing: Omit<Briefing, 'documents'>) {
    const taken = documents.read;
    conversation.append(you(said, taken.map(noteOf)));
    const outcome = await generation.generate(description, {
      ...briefing,
      documents: taken.map(planDocumentOf),
    });
    if (outcome === null) return;
    if (outcome.team) team.adopt(outcome.team);
    conversation.append(outcome.reply);
  }

  /**
   * Answers the planner's questions, said in words as `said`, and plans with the
   * answers; no answers skips the questions. Either way it asks nothing more.
   */
  function answer(asked: QuestionsMessage, answers: PlanAnswer[], said: string) {
    if (busy || openQuestions(conversation.messages)?.id !== asked.id) return;
    conversation.update(asked.id, settleQuestions(answers.length ? 'answered' : 'skipped'));
    void plan(said, asked.description, { answers, mayAsk: false });
  }

  return { describe: (said: string) => void plan(said, said, FIRST_ASK), answer };
}

/** A message typed while the planner's questions are open answers all of them at once. */
function typedAnswer(asked: QuestionsMessage, text: string): PlanAnswer {
  return { question: asked.questions.map((item) => item.question).join('\n'), answer: text };
}

/**
 * The mission workspace's state: the team, the conversation about it, its proposals,
 * its runs and the documents added to it. What the person sends is routed here: the
 * first message describes the mission (a team is generated, or the planner asks
 * questions first, which the next message answers), "run it" asks for the run's inputs,
 * and anything else is a change request.
 */
export function useMission(routeId: number | undefined, seed: StoredMission) {
  const parts = useMissionParts(routeId, seed);
  const { team, conversation, generation, proposals, run, documents } = parts;
  const leaving = useRef(false);
  useAdoptedAddress(routeId, team.pipeline?.id, leaving);
  useReopenedGreeting(routeId !== undefined, team, conversation);
  const openInBuilder = useOpenInBuilder(team, leaving);

  const thinking = generation.generating || proposals.revision.busy;
  // A saved mission that is loading, or could not be loaded, cannot be talked to yet.
  const unavailable = team.status === 'loading' || (routeId !== undefined && !team.pipeline);
  // What is sent next plans the team (no team yet, or the planner's questions are open).
  const plansNext = team.pipeline === null || openQuestions(conversation.messages) !== null;
  const planWaitsFor = plansNext ? documents.reading : '';

  const { describe, answer } = useMissionPlanning(parts, thinking || planWaitsFor !== '');

  /** "Run it": the form opens with the documents read so far that fit; those leave the box. */
  function runIt(said?: string) {
    const taken = run.ask(said, documents.read);
    if (taken !== null) documents.release(taken);
  }

  /** Routes what the person typed; false when nothing can be sent right now. */
  function send(text: string): boolean {
    const said = text.trim();
    if (!said || thinking || unavailable || planWaitsFor) return false;
    const asked = openQuestions(conversation.messages);
    if (asked) answer(asked, [typedAnswer(asked, said)], said);
    else if (team.pipeline === null) describe(said);
    else if (isRunRequest(said)) runIt(said);
    else proposals.request(said);
    return true;
  }

  function startFromTemplate(template: MissionTemplate, created: Pipeline) {
    team.adopt(created);
    const reply = teamReply(describeTeam(created), 'template');
    conversation.append(you(`Start from the “${template.title}” template`), reply);
  }

  const state = { thinking, unavailable, planWaitsFor, ...documentsForRun(parts) };
  return { ...parts, ...state, send, answer, runIt, startFromTemplate, openInBuilder };
}

export type Mission = ReturnType<typeof useMission>;
