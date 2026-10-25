import { MessagesSquare, Plus } from 'lucide-react';
import { useEffect, useRef, useState, type Ref, type RefObject } from 'react';

import { Bubble, Working } from './Bubble';
import { MessageItem } from './MessageItem';
import type { MessageContext } from './messageContext';
import type { PaneId } from './missionPanes';
import { MissionComposer } from './MissionComposer';
import { MissionStart } from './MissionStart';
import { PaneHeader } from './PaneHeader';
import type { Mission } from './useMission';

interface ConversationPaneProps {
  mission: Mission;
  showPane: (pane: PaneId) => void;
  onStartOver: () => void;
}

const LOG_CLASS =
  'relative min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-5 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-sky-400/60 sm:px-5';

/** Why the message box cannot send right now, when it cannot. */
function composerHint(mission: Mission): string {
  if (mission.generation.generating) return 'AIMIx is putting your team together…';
  if (mission.proposals.revision.busy) return 'AIMIx is working on your change…';
  return mission.unavailable ? 'This mission is not available.' : '';
}

/** Scrolls the newest message into view as the conversation grows or an answer changes. */
function useFollowLog(mission: Mission) {
  const end = useRef<HTMLDivElement>(null);
  const { revision } = mission.proposals;
  const size = mission.conversation.messages.length;
  const answer = `${mission.generation.generating}-${revision.busy}-${revision.proposal !== null}`;
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: 'nearest' });
  }, [size, answer]);
  return end;
}

/** What the answers in the log need from the workspace to be drawn live. */
function contextOf(
  mission: Mission,
  showPane: (pane: PaneId) => void,
  field: RefObject<HTMLTextAreaElement | null>,
): MessageContext {
  const { team, followed } = mission;
  return {
    team: team.pipeline,
    proposals: mission.proposals,
    run: mission.run,
    latestRun: followed.run,
    runActive: followed.active,
    showPane,
    focusComposer: () => field.current?.focus(),
  };
}

interface MessageLogProps {
  mission: Mission;
  context: MessageContext;
  /** Nothing said yet: the log is an empty live region until the first message. */
  fresh: boolean;
  end: Ref<HTMLDivElement>;
}

/** The messages, as an ARIA log so AIMIx's answers are announced, and its work in progress. */
function MessageLog({ mission, context, fresh, end }: MessageLogProps) {
  const { generation, conversation } = mission;
  return (
    <div
      role="log"
      aria-label="Conversation with AIMIx"
      tabIndex={fresh ? undefined : 0}
      className={fresh ? '' : LOG_CLASS}
    >
      {conversation.messages.map((message) => (
        <MessageItem key={message.id} message={message} context={context} />
      ))}
      {generation.generating && (
        <Bubble>
          <Working onStop={generation.cancel}>Putting your team together…</Working>
        </Bubble>
      )}
      <div ref={end} />
    </div>
  );
}

function StartOver({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1 text-xs font-medium text-slate-200 transition-colors hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400"
    >
      <Plus aria-hidden="true" className="size-3.5" />
      New mission
    </button>
  );
}

/**
 * The conversation with AIMIx: the empty state that asks for a mission, the log of
 * messages, and the message box.
 */
export function ConversationPane({ mission, showPane, onStartOver }: ConversationPaneProps) {
  const [text, setText] = useState('');
  const field = useRef<HTMLTextAreaElement>(null);
  const end = useFollowLog(mission);
  const { team, run, followed } = mission;
  const fresh =
    mission.conversation.messages.length === 0 && team.pipeline === null && !mission.unavailable;
  const canRun =
    team.pipeline !== null && !mission.thinking && run.formId === null && !followed.active;

  function send() {
    if (mission.send(text)) setText('');
  }

  function pick(example: string) {
    setText(example);
    field.current?.focus();
  }

  return (
    <>
      <PaneHeader pane="chat" icon={MessagesSquare}>
        {!fresh && <StartOver onClick={onStartOver} />}
      </PaneHeader>
      {fresh && <MissionStart onExample={pick} onTemplate={mission.startFromTemplate} />}
      <MessageLog
        mission={mission}
        context={contextOf(mission, showPane, field)}
        fresh={fresh}
        end={end}
      />
      <MissionComposer
        ref={field}
        value={text}
        onChange={setText}
        onSend={send}
        hasTeam={team.pipeline !== null}
        disabled={mission.thinking || mission.unavailable}
        disabledHint={composerHint(mission)}
        onRun={canRun ? () => run.ask() : undefined}
      />
    </>
  );
}
