import { useCallback, useState } from 'react';

import { ApiError } from '../../core/api/client';
import { planMission } from '../../core/api/pipelines';
import type { Pipeline, PlanAnswer } from '../../core/api/types';
import { useCancellableRequest } from '../../core/hooks/useCancellableRequest';
import { note, questionsReply, teamReply, type AimixMessage } from './missionMessages';
import { describeTeam } from './teamBrief';

/** What a description turned into: the team, if one was made, and AIMIx's answer (the
 * team in words, or the planner's questions when it needs to know more first). */
export interface Generation {
  team: Pipeline | null;
  reply: AimixMessage;
}

/** How many words of the description name a mission the planner left unnamed. */
const NAME_WORDS = 8;

/** Plainer words for failures a person can act on; anything else keeps the server's message. */
const FRIENDLY_FAILURES: Record<string, string> = {
  upstream_response_invalid: 'I could not turn that into a team. Try describing it another way.',
};

export const GENERATION_STOPPED = 'Stopped. Describe your mission again whenever you are ready.';

function failure(cause: unknown): string {
  if (cause instanceof ApiError) return FRIENDLY_FAILURES[cause.code] ?? cause.message;
  return 'I could not put a team together just now. Please try again.';
}

/** The plan, named from the description's first words when the planner gave no name. */
export function missionNamed(pipeline: Pipeline, description: string): Pipeline {
  if (pipeline.name.trim()) return pipeline;
  return { ...pipeline, name: description.trim().split(/\s+/).slice(0, NAME_WORDS).join(' ') };
}

/**
 * How the planner is asked: `answers` to the questions it asked before, and whether it
 * may ask (it may not once the person skipped its questions).
 */
export interface Briefing {
  answers: PlanAnswer[];
  mayAsk: boolean;
}

const FIRST_ASK: Briefing = { answers: [], mayAsk: true };

async function plan(
  description: string,
  briefing: Briefing,
  signal: AbortSignal,
): Promise<Generation> {
  try {
    const response = await planMission(description, briefing.answers, briefing.mayAsk, signal);
    if (response.generated_pipeline === null) {
      return { team: null, reply: questionsReply(description, response.questions) };
    }
    const team = missionNamed(response.generated_pipeline, description);
    return { team, reply: teamReply(describeTeam(team), 'generated') };
  } catch (cause) {
    return {
      team: null,
      reply: signal.aborted ? note(GENERATION_STOPPED) : note(failure(cause), 'error'),
    };
  }
}

/**
 * Turns a mission description into a team (POST /api/pipelines/generate), or into the
 * planner's questions when the description leaves too much open; nothing is saved. Stop cancels the request and answers "Stopped."; leaving the screen cancels it
 * and resolves to null, so nothing is said to a screen that is gone.
 */
export function useTeamGeneration() {
  const [generating, setGenerating] = useState(false);
  const { start, cancel, finish } = useCancellableRequest();

  const generate = useCallback(
    async (description: string, briefing = FIRST_ASK): Promise<Generation | null> => {
      const controller = start();
      setGenerating(true);
      const outcome = await plan(description, briefing, controller.signal);
      if (!finish(controller)) return null;
      setGenerating(false);
      return outcome;
    },
    [finish, start],
  );

  return { generating, generate, cancel };
}
