import { Mic, Square } from 'lucide-react';

import { Spinner } from '../ui/Spinner';
import { canRecordVoice, useVoiceInput } from './useVoiceInput';

interface MicButtonProps {
  /** What dictating does here, for screen readers and the tooltip: "Dictate your mission". */
  label: string;
  /** Gets the words once the clip is transcribed. */
  onTranscript: (text: string) => void;
}

function clock(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

const IDLE_STYLE =
  'border-white/10 bg-white/5 text-slate-300 hover:border-sky-400/40 hover:text-white';
const RECORDING_STYLE = 'border-rose-400/50 bg-rose-500/15 text-rose-200';

/**
 * Records a spoken message and hands back its text: press to speak, press again to stop.
 * Hidden where the browser cannot record.
 */
export function MicButton({ label, onTranscript }: MicButtonProps) {
  const voice = useVoiceInput(onTranscript);
  if (!canRecordVoice()) return null;

  const recording = voice.state === 'recording';
  const busy = voice.state === 'transcribing';
  const status = recording ? 'Recording' : busy ? 'Transcribing your recording' : '';
  return (
    <div className="relative flex shrink-0 items-center gap-2">
      {recording && (
        <span className="text-xs text-rose-200 tabular-nums">{clock(voice.seconds)}</span>
      )}
      <button
        type="button"
        onClick={recording ? voice.stop : voice.start}
        disabled={busy}
        aria-label={recording ? 'Stop recording' : busy ? status : label}
        title={recording ? 'Stop recording' : label}
        className={`grid size-10 place-items-center rounded-xl border transition duration-300 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 disabled:cursor-wait ${recording ? RECORDING_STYLE : IDLE_STYLE}`}
      >
        {busy ? (
          <Spinner decorative className="size-4" />
        ) : recording ? (
          <Square aria-hidden="true" className="size-4 fill-current motion-safe:animate-pulse" />
        ) : (
          <Mic aria-hidden="true" className="size-5" />
        )}
      </button>
      <span className="sr-only" aria-live="polite">
        {status}
      </span>
      {voice.error && (
        <p
          role="alert"
          className="absolute right-0 bottom-full z-10 mb-2 w-64 rounded-lg border border-rose-400/30 bg-slate-950/95 px-3 py-2 text-xs text-rose-200 shadow-lg"
        >
          {voice.error}
        </p>
      )}
    </div>
  );
}
