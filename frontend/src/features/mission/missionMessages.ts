import type { PipelineChange } from '../../core/api/types';
import type { TeamBrief } from './teamBrief';

/**
 * The mission conversation as plain data: what the person said and what AIMIx answered.
 * Every message is JSON, so the conversation can be kept for the tab (missionStorage).
 */

/** What the person typed, or the action they took (e.g. "Run it"). */
export interface YouMessage {
  id: string;
  from: 'you';
  text: string;
}

export const NOTE_TONES = ['info', 'error'] as const;

/** A plain answer; `error` when it reports something that went wrong. */
export interface NoteMessage {
  id: string;
  from: 'aimix';
  kind: 'note';
  text: string;
  tone: (typeof NOTE_TONES)[number];
}

export const TEAM_ORIGINS = ['generated', 'template', 'reopened'] as const;

/** A team, described in plain words as it was when AIMIx presented it. */
export interface TeamMessage {
  id: string;
  from: 'aimix';
  kind: 'team';
  origin: (typeof TEAM_ORIGINS)[number];
  brief: TeamBrief;
}

/**
 * `pending` while the live proposal (useRevisePipeline) belongs to this answer; the
 * outcome is kept once the person applies or discards it, or the conversation moves on.
 */
export const PROPOSAL_STATES = [
  'pending',
  'applied',
  'discarded',
  'failed',
  'stopped',
  'expired',
] as const;
export type ProposalState = (typeof PROPOSAL_STATES)[number];

/** AIMIx's answer to a change request. */
export interface ProposalMessage {
  id: string;
  from: 'aimix';
  kind: 'proposal';
  state: ProposalState;
  changes: PipelineChange[];
  error: string;
}

/** `open` while the person fills it in; `started` once a run began from it. */
export const INPUTS_STATES = ['open', 'started', 'closed'] as const;
export type InputsState = (typeof INPUTS_STATES)[number];

/** The run form, asked for in the conversation. */
export interface InputsMessage {
  id: string;
  from: 'aimix';
  kind: 'inputs';
  state: InputsState;
}

/** A run started from the conversation; it is shown live while it is the mission's newest. */
export interface RunMessage {
  id: string;
  from: 'aimix';
  kind: 'run';
  runId: number;
}

export type AimixMessage = NoteMessage | TeamMessage | ProposalMessage | InputsMessage | RunMessage;
export type MissionMessage = YouMessage | AimixMessage;

/** Unique enough for one conversation; `randomUUID` is missing outside secure contexts. */
export function newMessageId(): string {
  return (
    globalThis.crypto?.randomUUID?.() ??
    `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
  );
}

export function you(text: string): YouMessage {
  return { id: newMessageId(), from: 'you', text };
}

export function note(text: string, tone: NoteMessage['tone'] = 'info'): NoteMessage {
  return { id: newMessageId(), from: 'aimix', kind: 'note', text, tone };
}

export function teamReply(brief: TeamBrief, origin: TeamMessage['origin']): TeamMessage {
  return { id: newMessageId(), from: 'aimix', kind: 'team', origin, brief };
}

export function pendingProposal(): ProposalMessage {
  return {
    id: newMessageId(),
    from: 'aimix',
    kind: 'proposal',
    state: 'pending',
    changes: [],
    error: '',
  };
}

export function inputsRequest(): InputsMessage {
  return { id: newMessageId(), from: 'aimix', kind: 'inputs', state: 'open' };
}

export function runReply(runId: number): RunMessage {
  return { id: newMessageId(), from: 'aimix', kind: 'run', runId };
}

export type ProposalOutcome = Pick<ProposalMessage, 'state'> &
  Partial<Pick<ProposalMessage, 'changes' | 'error'>>;

/** An update for `Conversation.update` that settles a proposal answer. */
export function settleProposal(outcome: ProposalOutcome) {
  return (message: MissionMessage): MissionMessage =>
    message.from === 'aimix' && message.kind === 'proposal' ? { ...message, ...outcome } : message;
}

/** An update for `Conversation.update` that changes a run form's state. */
export function settleInputs(state: InputsState) {
  return (message: MissionMessage): MissionMessage =>
    message.from === 'aimix' && message.kind === 'inputs' ? { ...message, state } : message;
}

/** The run form the person can still fill in: the newest open one. */
export function openInputsId(messages: MissionMessage[]): string | null {
  const open = messages.filter(
    (message) => message.from === 'aimix' && message.kind === 'inputs' && message.state === 'open',
  );
  return open.at(-1)?.id ?? null;
}

const UNANSWERED =
  'The page was left before I could answer your last message. Send it again if you still need it.';

/** A conversation as restored: a message left unanswered (the page was left) is said to be. */
export function restoredMessages(messages: MissionMessage[]): MissionMessage[] {
  return messages.at(-1)?.from === 'you' ? [...messages, note(UNANSWERED)] : messages;
}
