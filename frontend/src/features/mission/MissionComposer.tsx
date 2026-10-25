import { Play, SendHorizontal } from 'lucide-react';
import { useId, type KeyboardEvent, type Ref, type SyntheticEvent } from 'react';

import { GlowButton } from '../../core/ui/GlowButton';
import { REVISION_INSTRUCTION_MAX_LENGTH } from '../pipelines/revision';

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
  ref?: Ref<HTMLTextAreaElement>;
}

interface FieldProps extends Pick<MissionComposerProps, 'value' | 'onChange' | 'hasTeam' | 'ref'> {
  id: string;
  ready: boolean;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
}

/** The labelled text box with its send button. */
function ComposerField({ id, value, onChange, hasTeam, ready, onKeyDown, ref }: FieldProps) {
  return (
    <>
      <label htmlFor={`${id}-message`} className="sr-only">
        {hasTeam ? 'Message AIMIx about your team' : 'Describe your mission'}
      </label>
      <div className="flex items-end gap-2 rounded-2xl border border-white/10 bg-slate-900/70 p-2 transition-[border-color,box-shadow] focus-within:border-sky-400/50 focus-within:shadow-[0_0_0_4px_rgba(56,189,248,0.08)]">
        <textarea
          ref={ref}
          id={`${id}-message`}
          rows={2}
          value={value}
          maxLength={hasTeam ? REVISION_INSTRUCTION_MAX_LENGTH : undefined}
          aria-describedby={`${id}-hint`}
          placeholder={
            hasTeam ? 'Ask for a change, or say “run it”' : 'Describe what you want to get done…'
          }
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={onKeyDown}
          className="max-h-40 min-h-11 min-w-0 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-white outline-none placeholder:text-slate-400"
        />
        <button
          type="submit"
          disabled={!ready}
          aria-label="Send"
          className="grid size-10 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-sky-600 via-indigo-600 to-purple-600 text-white transition duration-300 enabled:hover:shadow-[0_0_24px_rgba(99,102,241,0.6)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <SendHorizontal aria-hidden="true" className="size-5" />
        </button>
      </div>
    </>
  );
}

/**
 * The message box: Enter sends, Shift + Enter starts a new line. "Run it" sits under it
 * whenever the team can run; typing "run it" does the same.
 */
export function MissionComposer({
  value,
  onChange,
  onSend,
  hasTeam,
  disabled,
  disabledHint,
  onRun,
  ref,
}: MissionComposerProps) {
  const id = useId();
  const ready = !disabled && value.trim() !== '';

  function submit(event: SyntheticEvent) {
    event.preventDefault();
    if (ready) onSend();
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return;
    submit(event);
  }

  return (
    <form onSubmit={submit} className="shrink-0 border-t border-white/[0.06] p-3 sm:p-4">
      <ComposerField {...{ id, value, onChange, hasTeam, ready, onKeyDown, ref }} />
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2">
        {onRun && (
          <GlowButton size="sm" onClick={onRun}>
            <Play aria-hidden="true" className="size-4" />
            Run it
          </GlowButton>
        )}
        <p id={`${id}-hint`} className="text-xs text-slate-400">
          {disabled && disabledHint ? disabledHint : 'Enter sends · Shift + Enter adds a line'}
        </p>
      </div>
    </form>
  );
}
