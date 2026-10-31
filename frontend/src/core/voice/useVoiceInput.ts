import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiError } from '../api/client';
import { transcribeClip } from '../api/voice';
import { useLatest } from '../hooks/useLatest';
import { useMountedRef } from '../hooks/useMountedRef';
import { toSpeechWav } from './wav';

/** A recording stops by itself after this long, well inside the server's VOICE_MAX_BYTES. */
export const MAX_RECORDING_SECONDS = 180;

export type VoiceState = 'idle' | 'recording' | 'transcribing';

export interface VoiceInput {
  state: VoiceState;
  /** Whole seconds recorded so far. */
  seconds: number;
  /** Why the last try failed, said to the user; null when it did not fail. */
  error: string | null;
  start: () => void;
  stop: () => void;
}

/** One recording: the microphone it holds, its pieces, and the transcription it leads to. */
interface Session {
  recorder: MediaRecorder;
  stream: MediaStream;
  chunks: Blob[];
  timer: number;
  abort: AbortController;
}

/** Whether this browser can record a clip and convert it for the speech model. */
export function canRecordVoice(): boolean {
  return (
    typeof navigator !== 'undefined' &&
    typeof navigator.mediaDevices?.getUserMedia === 'function' &&
    typeof MediaRecorder !== 'undefined' &&
    typeof OfflineAudioContext !== 'undefined'
  );
}

function microphoneError(cause: unknown): string {
  const name = cause instanceof DOMException ? cause.name : '';
  if (name === 'NotAllowedError') {
    return 'Microphone access was refused. Allow it in your browser to dictate.';
  }
  if (name === 'NotFoundError') return 'No microphone was found.';
  return 'The microphone could not be started.';
}

function stopTracks(stream: MediaStream): void {
  stream.getTracks().forEach((track) => track.stop());
}

function release(session: Session): void {
  window.clearInterval(session.timer);
  stopTracks(session.stream);
}

function finish(session: Session): void {
  if (session.recorder.state !== 'inactive') session.recorder.stop();
}

/** Starts recording `stream`: `onTick` hears the seconds, `onClip` gets the clip once it stops. */
function record(
  stream: MediaStream,
  onTick: (seconds: number) => void,
  onClip: (clip: Blob, session: Session) => void,
): Session {
  const recorder = new MediaRecorder(stream);
  const session: Session = { recorder, stream, chunks: [], timer: 0, abort: new AbortController() };
  const startedAt = Date.now();
  recorder.ondataavailable = (event) => {
    if (event.data.size > 0) session.chunks.push(event.data);
  };
  recorder.onstop = () => {
    release(session);
    if (!session.abort.signal.aborted) {
      onClip(new Blob(session.chunks, { type: recorder.mimeType }), session);
    }
  };
  session.timer = window.setInterval(() => {
    const seconds = Math.floor((Date.now() - startedAt) / 1000);
    onTick(seconds);
    if (seconds >= MAX_RECORDING_SECONDS) finish(session);
  }, 250);
  recorder.start();
  return session;
}

/**
 * Dictation: `start` records from the microphone, `stop` ends the clip, and its text
 * goes to `onTranscript` (the latest one passed). Unmounting releases the microphone and
 * drops a transcription still on its way.
 */
export function useVoiceInput(onTranscript: (text: string) => void): VoiceInput {
  const [state, setState] = useState<VoiceState>('idle');
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const deliver = useLatest(onTranscript);
  const mounted = useMountedRef();
  const session = useRef<Session | null>(null);

  const transcribe = useCallback(
    async (clip: Blob, current: Session) => {
      const { signal } = current.abort;
      try {
        if (!clip.size) {
          setError('Nothing was recorded. Try again.');
          return;
        }
        const { transcript } = await transcribeClip(await toSpeechWav(clip), signal);
        const text = transcript.trim();
        if (signal.aborted) return;
        if (text) deliver.current(text);
        else setError('No speech was heard. Try again, closer to the microphone.');
      } catch (cause) {
        if (!signal.aborted) {
          setError(cause instanceof ApiError ? cause.message : 'The recording could not be read.');
        }
      } finally {
        if (session.current === current) session.current = null;
        if (!signal.aborted) setState('idle');
      }
    },
    [deliver],
  );

  const begin = useCallback(async () => {
    if (session.current) return;
    setError(null);
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (cause) {
      setError(microphoneError(cause));
      return;
    }
    if (!mounted.current) {
      stopTracks(stream);
      return;
    }
    session.current = record(stream, setSeconds, (clip, current) => {
      setState('transcribing');
      void transcribe(clip, current);
    });
    setSeconds(0);
    setState('recording');
  }, [mounted, transcribe]);

  const stop = useCallback(() => {
    if (session.current) finish(session.current);
  }, []);

  useEffect(
    () => () => {
      const current = session.current;
      if (!current) return;
      current.abort.abort();
      finish(current);
      release(current);
    },
    [],
  );

  const start = useCallback(() => void begin(), [begin]);
  return { state, seconds, error, start, stop };
}
