/**
 * The only audio Meta's speech model reads is WAV: mono, 16-bit PCM, at 16 or 24 kHz
 * (backend/api/services/voice.py checks it). Browsers record WebM, Ogg or MP4, so a
 * clip is decoded and re-rendered here before it is sent.
 */
export const SPEECH_SAMPLE_RATE = 16_000;

const HEADER_BYTES = 44;

/** A recorded clip, in whatever format the browser recorded it, as 16 kHz mono WAV. */
export async function toSpeechWav(recording: Blob): Promise<Blob> {
  const context = new AudioContext();
  let decoded: AudioBuffer;
  try {
    decoded = await context.decodeAudioData(await recording.arrayBuffer());
  } finally {
    void context.close();
  }
  const frames = Math.max(1, Math.ceil(decoded.duration * SPEECH_SAMPLE_RATE));
  // One output channel: rendering down-mixes a stereo recording and resamples it.
  const offline = new OfflineAudioContext(1, frames, SPEECH_SAMPLE_RATE);
  const source = offline.createBufferSource();
  source.buffer = decoded;
  source.connect(offline.destination);
  source.start();
  const rendered = await offline.startRendering();
  return encodeWav(rendered.getChannelData(0), SPEECH_SAMPLE_RATE);
}

/** Mono samples in [-1, 1] as a 16-bit PCM WAV file. */
export function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const dataBytes = samples.length * 2;
  const view = new DataView(new ArrayBuffer(HEADER_BYTES + dataBytes));
  const ascii = (offset: number, text: string) => {
    for (let index = 0; index < text.length; index += 1) {
      view.setUint8(offset + index, text.charCodeAt(index));
    }
  };
  ascii(0, 'RIFF');
  view.setUint32(4, HEADER_BYTES - 8 + dataBytes, true);
  ascii(8, 'WAVE');
  ascii(12, 'fmt ');
  view.setUint32(16, 16, true); // the size of this format chunk
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // bytes per second
  view.setUint16(32, 2, true); // bytes per frame
  view.setUint16(34, 16, true); // bits per sample
  ascii(36, 'data');
  view.setUint32(40, dataBytes, true);
  samples.forEach((sample, index) => {
    const clamped = Math.max(-1, Math.min(1, sample));
    view.setInt16(
      HEADER_BYTES + index * 2,
      clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff,
      true,
    );
  });
  return new Blob([view.buffer], { type: 'audio/wav' });
}
