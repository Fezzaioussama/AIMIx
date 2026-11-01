import { FileText, Globe, Sparkles } from 'lucide-react';
import { motion } from 'motion/react';
import type { ReactNode } from 'react';

import { documentSize } from '../pipelines/pipelineInputs';
import { isWebAddress, sourceLabel } from '../pipelines/webLinks';
import { Bubble } from './Bubble';
import { InputsMessageView } from './InputsMessageView';
import type { MessageContext, ViewProps } from './messageContext';
import type { AimixMessage, DocumentNote, MissionMessage, YouMessage } from './missionMessages';
import { ProposalMessageView } from './ProposalMessageView';
import { QuestionsMessageView } from './QuestionsMessageView';
import { RunMessageView } from './RunMessageView';
import { TeamMessageView } from './TeamMessageView';

function NoteView({ message }: ViewProps<'note'>) {
  return <Bubble tone={message.tone}>{message.text}</Bubble>;
}

/** One view per kind of answer (Strategy + Registry): a new kind is a new entry. */
const VIEWS: { [K in AimixMessage['kind']]: (props: ViewProps<K>) => ReactNode } = {
  note: NoteView,
  team: TeamMessageView,
  questions: QuestionsMessageView,
  proposal: ProposalMessageView,
  inputs: InputsMessageView,
  run: RunMessageView,
};

type AnyView = (props: { message: AimixMessage; context: MessageContext }) => ReactNode;

const ENTER = { initial: { opacity: 0, y: 10 }, animate: { opacity: 1, y: 0 } } as const;
const SPRING = { type: 'spring', stiffness: 380, damping: 32 } as const;

/** The documents that went with a message: their names and sizes, never their text. */
function SentDocuments({ documents }: { documents: DocumentNote[] }) {
  return (
    <ul aria-label="Attached" className="mt-2 flex flex-wrap justify-end gap-1.5">
      {documents.map((note, index) => {
        const Icon = isWebAddress(note.name) ? Globe : FileText;
        return (
          <li
            key={`${index}-${note.name}`}
            className="inline-flex max-w-full min-w-0 items-center gap-1.5 rounded-lg bg-white/15 px-2 py-1 text-xs"
          >
            <Icon aria-hidden="true" className="size-3.5 shrink-0" />
            <span title={note.name} className="min-w-0 truncate font-medium">
              {sourceLabel(note.name)}
            </span>
            <span className="shrink-0 text-white/85">{documentSize(note)}</span>
          </li>
        );
      })}
    </ul>
  );
}

function YouSaid({ message }: { message: YouMessage }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] min-w-0 rounded-2xl rounded-br-md bg-gradient-to-br from-sky-700 via-indigo-600 to-purple-600 px-4 py-2.5 text-sm leading-relaxed text-white shadow-[0_8px_24px_-12px_rgba(99,102,241,0.7)]">
        <p className="break-words whitespace-pre-wrap">
          <span className="sr-only">You said: </span>
          {message.text}
        </p>
        {message.documents && <SentDocuments documents={message.documents} />}
      </div>
    </div>
  );
}

function AimixSaid({ message, context }: { message: AimixMessage; context: MessageContext }) {
  // TypeScript cannot pair a union member with its view; VIEWS is checked above.
  const View = VIEWS[message.kind] as AnyView;
  return (
    <div>
      <p className="mb-1.5 flex items-center gap-2 text-xs font-semibold text-slate-300">
        <span
          aria-hidden="true"
          className="grid size-5 place-items-center rounded-full bg-gradient-to-br from-sky-400 via-indigo-500 to-purple-500"
        >
          <Sparkles className="size-3 text-white" />
        </span>
        AIMIx
      </p>
      <div className="space-y-3">
        <View message={message} context={context} />
      </div>
    </div>
  );
}

/** One line of the conversation: what the person said, or AIMIx's answer. */
export function MessageItem({
  message,
  context,
}: {
  message: MissionMessage;
  context: MessageContext;
}) {
  return (
    <motion.div {...ENTER} transition={SPRING}>
      {message.from === 'you' ? (
        <YouSaid message={message} />
      ) : (
        <AimixSaid message={message} context={context} />
      )}
    </motion.div>
  );
}
