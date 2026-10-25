import { useCallback, useEffect, useRef, useState } from 'react';

import type { Pipeline } from '../../core/api/types';
import type { MissionMessage } from './missionMessages';
import { forgetMission, missionKey, writeMission } from './missionStorage';

export interface Conversation {
  messages: MissionMessage[];
  append: (...added: MissionMessage[]) => void;
  /** Changes one message in place, e.g. a proposal once it is applied. */
  update: (id: string, change: (message: MissionMessage) => MissionMessage) => void;
}

/**
 * The mission's conversation, kept for this tab in sessionStorage under the mission's
 * key, with the team of a mission never saved (`draft`). When that mission is saved
 * and gets an id, the conversation moves to the id's key and the draft's is cleared.
 */
export function useMissionConversation(
  pipelineId: number | undefined,
  initial: MissionMessage[],
  draft: Pipeline | null,
): Conversation {
  const [messages, setMessages] = useState(initial);
  const key = missionKey(pipelineId);
  const storedUnder = useRef(key);

  useEffect(() => {
    writeMission(key, { messages, draft: pipelineId === undefined ? draft : null });
    if (storedUnder.current !== key && storedUnder.current === missionKey()) {
      forgetMission(storedUnder.current);
    }
    storedUnder.current = key;
  }, [draft, key, messages, pipelineId]);

  const append = useCallback((...added: MissionMessage[]) => {
    setMessages((current) => [...current, ...added]);
  }, []);

  const update = useCallback((id: string, change: (message: MissionMessage) => MissionMessage) => {
    setMessages((current) =>
      current.map((message) => (message.id === id ? change(message) : message)),
    );
  }, []);

  return { messages, append, update };
}
