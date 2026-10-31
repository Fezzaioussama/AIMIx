import { API } from './endpoints';
import { request, UPLOAD_TIMEOUT_MS } from './client';
import type { Transcript } from './types';

/**
 * Has the server turn one recorded clip (16 kHz mono 16-bit WAV, see core/voice/wav.ts)
 * into text with Meta's speech model. Nothing is stored: the caller puts the text in a
 * message box.
 */
export function transcribeClip(wav: Blob, signal?: AbortSignal): Promise<Transcript> {
  const form = new FormData();
  form.append('audio', wav, 'clip.wav');
  return request<Transcript>(API.transcribeVoice, {
    method: 'POST',
    body: form,
    timeoutMs: UPLOAD_TIMEOUT_MS,
    signal,
  });
}
