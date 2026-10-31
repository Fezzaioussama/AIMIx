import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/client';
import { transcribeClip } from '../api/voice';
import { MicButton } from './MicButton';
import { toSpeechWav } from './wav';

vi.mock('../api/voice', () => ({ transcribeClip: vi.fn() }));
vi.mock('./wav', () => ({ toSpeechWav: vi.fn() }));

/** A MediaRecorder that hands over one piece of audio when stopped. */
class FakeRecorder {
  state: RecordingState = 'inactive';
  mimeType = 'audio/webm';
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;

  start(): void {
    this.state = 'recording';
  }

  stop(): void {
    this.state = 'inactive';
    this.ondataavailable?.({ data: new Blob(['spoken words']) });
    this.onstop?.();
  }
}

const track = { stop: vi.fn() };
const getUserMedia = vi.fn();
const LABEL = 'Dictate your mission';

beforeEach(() => {
  vi.stubGlobal('MediaRecorder', FakeRecorder);
  vi.stubGlobal('OfflineAudioContext', class {});
  Object.defineProperty(navigator, 'mediaDevices', {
    value: { getUserMedia },
    configurable: true,
  });
  getUserMedia.mockResolvedValue({ getTracks: () => [track] });
  vi.mocked(toSpeechWav).mockResolvedValue(new Blob(['RIFF'], { type: 'audio/wav' }));
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  Reflect.deleteProperty(navigator, 'mediaDevices');
});

async function recordAndStop(onTranscript = vi.fn()) {
  const user = userEvent.setup();
  render(<MicButton label={LABEL} onTranscript={onTranscript} />);
  await user.click(screen.getByRole('button', { name: LABEL }));
  await user.click(await screen.findByRole('button', { name: 'Stop recording' }));
  return onTranscript;
}

describe('MicButton', () => {
  it('records, has the clip transcribed and hands back the words', async () => {
    vi.mocked(transcribeClip).mockResolvedValue({
      transcript: ' Build a research team ',
      duration_ms: 1800,
    });

    const onTranscript = await recordAndStop();

    await waitFor(() => expect(onTranscript).toHaveBeenCalledWith('Build a research team'));
    expect(toSpeechWav).toHaveBeenCalledWith(expect.any(Blob));
    expect(track.stop).toHaveBeenCalled();
    expect(await screen.findByRole('button', { name: LABEL })).toBeEnabled();
  });

  it('says when the microphone is refused', async () => {
    getUserMedia.mockRejectedValue(new DOMException('denied', 'NotAllowedError'));
    const user = userEvent.setup();
    render(<MicButton label={LABEL} onTranscript={vi.fn()} />);

    await user.click(screen.getByRole('button', { name: LABEL }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Microphone access was refused');
  });

  it('shows why the server could not transcribe the clip', async () => {
    vi.mocked(transcribeClip).mockRejectedValue(
      new ApiError(
        'No API key is set for meta. Add one on the Settings page.',
        503,
        'provider_not_configured',
      ),
    );

    const onTranscript = await recordAndStop();

    expect(await screen.findByRole('alert')).toHaveTextContent('Add one on the Settings page.');
    expect(onTranscript).not.toHaveBeenCalled();
  });

  it('says when no speech was heard', async () => {
    vi.mocked(transcribeClip).mockResolvedValue({ transcript: '  ', duration_ms: 900 });

    const onTranscript = await recordAndStop();

    expect(await screen.findByRole('alert')).toHaveTextContent('No speech was heard');
    expect(onTranscript).not.toHaveBeenCalled();
  });

  it('releases the microphone and sends nothing when it unmounts mid-recording', async () => {
    const user = userEvent.setup();
    const { unmount } = render(<MicButton label={LABEL} onTranscript={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: LABEL }));
    await screen.findByRole('button', { name: 'Stop recording' });

    unmount();

    expect(track.stop).toHaveBeenCalled();
    expect(transcribeClip).not.toHaveBeenCalled();
  });

  it('is hidden where the browser cannot record', () => {
    vi.stubGlobal('MediaRecorder', undefined);

    const { container } = render(<MicButton label={LABEL} onTranscript={vi.fn()} />);

    expect(container).toBeEmptyDOMElement();
  });
});
