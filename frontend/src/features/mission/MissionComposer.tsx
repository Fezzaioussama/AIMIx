import { Globe, Play } from 'lucide-react';
import { useId, type KeyboardEvent, type RefObject, type SyntheticEvent } from 'react';

import { PLAN_DESCRIPTION_MAX_LENGTH } from '../../core/api/pipelines';
import { useFileDrop } from '../../core/hooks/useFileDrop';
import { GlowButton } from '../../core/ui/GlowButton';
import { formatCount } from '../../core/usageFormat';
import { appendDictation } from '../../core/voice/dictation';
import { REVISION_INSTRUCTION_MAX_LENGTH } from '../pipelines/revision';
import { WebPageField } from '../pipelines/WebPageField';
import { linkHost } from '../pipelines/webLinks';
import { ComposerAttachments } from './ComposerAttachments';
import { ComposerToolbar, useLinkField } from './ComposerTools';
import { unattachedLink, type DocumentPlacement } from './missionDocuments';
import type { MissionDocuments } from './useMissionDocuments';

interface MissionComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  /** There is a team, so a message is a change request (or "run it"). */
  hasTeam: boolean;
  /** Nothing can be sent now: AIMIx is working, or the mission is not available. */
  disabled: boolean;
  /** Why nothing can be sent, said under the box. */
  disabledHint?: string;
  /** Offered when the team can run now. */
  onRun?: () => void;
  /** The documents and web pages added to the mission, shown as chips above the text. */
  documents: MissionDocuments;
  /** Read documents an open run form did not take, and why. */
  placement?: DocumentPlacement | null;
  /** The text box: the pane focuses it, and so does the box when a chip or link goes. */
  ref: RefObject<HTMLTextAreaElement | null>;
}

interface FieldProps extends Pick<
  MissionComposerProps,
  'value' | 'onChange' | 'hasTeam' | 'documents' | 'placement' | 'ref'
> {
  id: string;
  ready: boolean;
  maxLength: number;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
}

const BOX =
  'rounded-2xl border p-2 transition-[border-color,box-shadow,background-color] focus-within:border-sky-400/50 focus-within:shadow-[0_0_0_4px_rgba(56,189,248,0.08)]';

/** What the box says once it is full: the server takes no more. */
const FULL_BOX = {
  team: `That’s the most a change request takes (${formatCount(REVISION_INSTRUCTION_MAX_LENGTH)} characters).`,
  mission: `That’s the most a mission description takes (${formatCount(PLAN_DESCRIPTION_MAX_LENGTH)} characters). Attach long text as a document instead.`,
};

type TextProps = Omit<FieldProps, 'ready' | 'documents' | 'placement'>;

/** The text itself: a mission before there is a team, a change request after. */
function MessageText({ id, value, onChange, hasTeam, maxLength, onKeyDown, ref }: TextProps) {
  return (
    <textarea
      ref={ref}
      id={`${id}-message`}
      rows={2}
      value={value}
      maxLength={maxLength}
      aria-describedby={`${id}-hint`}
      placeholder={
        hasTeam ? 'Ask for a change, or say “run it”' : 'Describe what you want to get done…'
      }
      onChange={(event) => onChange(event.target.value)}
      onKeyDown={onKeyDown}
      className="block max-h-40 min-h-11 w-full resize-none bg-transparent px-2 py-1.5 text-sm text-white outline-none placeholder:text-slate-400"
    />
  );
}

/**
 * The bordered box: the mission's documents, the link field, the text and its tools.
 * Files dropped on it are attached; it lights up while they are held over it.
 */
function ComposerField(props: FieldProps) {
  const { id, value, onChange, hasTeam, ready, maxLength, onKeyDown, documents, ref } = props;
  const { placement = null } = props;
  const link = useLinkField(`${id}-link`);
  const drop = useFileDrop(documents.addFiles);
  return (
    <>
      <label htmlFor={`${id}-message`} className="sr-only">
        {hasTeam ? 'Message AIMIx about your team' : 'Describe your mission'}
      </label>
      <div
        {...drop.zone}
        data-dropping={drop.dragging}
        className={`${BOX} ${drop.dragging ? 'border-sky-400/70 bg-sky-400/[0.08]' : 'border-white/10 bg-slate-900/70'}`}
      >
        <ComposerAttachments
          documents={documents}
          hasTeam={hasTeam}
          placement={placement}
          onEmptied={() => ref.current?.focus()}
        />
        <WebPageField
          id={link.id}
          open={link.open}
          busy={documents.full}
          onRead={(address) => {
            documents.addLink(address);
            link.close();
          }}
          onClose={link.close}
        />
        <MessageText {...{ id, value, onChange, hasTeam, maxLength, onKeyDown, ref }} />
        <ComposerToolbar
          onFiles={documents.addFiles}
          link={link}
          micLabel={hasTeam ? 'Dictate a change to your team' : 'Dictate your mission'}
          onTranscript={(text) => onChange(appendDictation(value, text, maxLength))}
          ready={ready}
        />
      </div>
    </>
  );
}

interface LinkSuggestionProps {
  text: string;
  documents: MissionDocuments;
  /** Called once the link is being read: the suggestion goes, so focus must go somewhere. */
  onRead: () => void;
}

/** Under the box: a link in the message that is not attached yet, offered to be read. */
function LinkSuggestion({ text, documents, onRead }: LinkSuggestionProps) {
  const link = unattachedLink(text, documents.items);
  if (link === null || documents.full) return null;
  return (
    <button
      type="button"
      onClick={() => {
        documents.addLink(link);
        onRead();
      }}
      className="mt-2 inline-flex min-h-11 items-center gap-1.5 rounded-lg px-1 text-xs font-medium text-sky-300 transition-colors hover:text-sky-200 focus-visible:outline-2 focus-visible:outline-sky-400 sm:min-h-0"
    >
      <Globe aria-hidden="true" className="size-3.5" />
      Read {linkHost(link)} for your team
    </button>
  );
}

/**
 * The message box: Enter sends, Shift + Enter adds a line. Documents and web pages added
 * here belong to the mission (the planner reads their start; the run gets them). "Run it"
 * sits under it whenever the team can run; typing "run it" does the same.
 */
export function MissionComposer({
  value,
  onChange,
  onSend,
  hasTeam,
  disabled,
  disabledHint,
  onRun,
  documents,
  placement,
  ref,
}: MissionComposerProps) {
  const id = useId();
  const ready = !disabled && value.trim() !== '';
  const maxLength = hasTeam ? REVISION_INSTRUCTION_MAX_LENGTH : PLAN_DESCRIPTION_MAX_LENGTH;
  const full = value.length >= maxLength ? FULL_BOX[hasTeam ? 'team' : 'mission'] : '';

  function submit(event: SyntheticEvent) {
    event.preventDefault();
    if (ready) onSend();
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return;
    submit(event);
  }

  return (
    // No browser validation: a half-typed link in the closed link field must not block Send.
    <form noValidate onSubmit={submit} className="shrink-0 border-t border-white/[0.06] p-3 sm:p-4">
      <ComposerField
        {...{
          id,
          value,
          onChange,
          hasTeam,
          ready,
          maxLength,
          onKeyDown,
          documents,
          placement,
          ref,
        }}
      />
      <LinkSuggestion text={value} documents={documents} onRead={() => ref.current?.focus()} />
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2">
        {onRun && (
          <GlowButton size="sm" onClick={onRun} className="pointer-coarse:min-h-11">
            <Play aria-hidden="true" className="size-4" />
            Run it
          </GlowButton>
        )}
        <p id={`${id}-hint`} className="text-xs text-slate-400">
          {disabled && disabledHint
            ? disabledHint
            : full || 'Enter sends · Shift + Enter adds a line'}
        </p>
      </div>
    </form>
  );
}
