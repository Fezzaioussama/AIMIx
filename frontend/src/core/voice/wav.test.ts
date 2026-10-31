import { describe, expect, it } from 'vitest';

import { encodeWav } from './wav';

/** The blob's bytes; jsdom's Blob has no arrayBuffer(), so read it the older way. */
function view(blob: Blob): Promise<DataView> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(new DataView(reader.result as ArrayBuffer));
    reader.onerror = () => reject(reader.error);
    reader.readAsArrayBuffer(blob);
  });
}

function ascii(bytes: DataView, offset: number): string {
  return String.fromCharCode(...[0, 1, 2, 3].map((index) => bytes.getUint8(offset + index)));
}

describe('encodeWav', () => {
  it('writes the mono 16-bit PCM header the speech model reads', async () => {
    const bytes = await view(encodeWav(new Float32Array(4), 16_000));

    expect([ascii(bytes, 0), ascii(bytes, 8), ascii(bytes, 12), ascii(bytes, 36)]).toEqual([
      'RIFF',
      'WAVE',
      'fmt ',
      'data',
    ]);
    expect(bytes.byteLength).toBe(44 + 8);
    expect(bytes.getUint16(20, true)).toBe(1); // PCM
    expect(bytes.getUint16(22, true)).toBe(1); // mono
    expect(bytes.getUint32(24, true)).toBe(16_000);
    expect(bytes.getUint16(34, true)).toBe(16);
    expect(bytes.getUint32(40, true)).toBe(8);
  });

  it('clamps samples to the 16-bit range', async () => {
    const bytes = await view(encodeWav(Float32Array.from([1, -1, 0, 2, -3]), 16_000));

    expect([0, 1, 2, 3, 4].map((index) => bytes.getInt16(44 + index * 2, true))).toEqual([
      32767, -32768, 0, 32767, -32768,
    ]);
  });
});
