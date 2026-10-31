import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { MissionComposer } from './MissionComposer';

// The microphone itself is covered in core/voice/MicButton.test.tsx: here it just speaks.
vi.mock('../../core/voice/MicButton', () => ({
  MicButton: ({ label, onTranscript }: { label: string; onTranscript: (text: string) => void }) => (
    <button type="button" onClick={() => onTranscript('then a reviewer checks it')}>
      {label}
    </button>
  ),
}));

function renderComposer(value: string, hasTeam: boolean) {
  const onChange = vi.fn();
  render(
    <MissionComposer
      value={value}
      onChange={onChange}
      onSend={vi.fn()}
      hasTeam={hasTeam}
      disabled={false}
    />,
  );
  return onChange;
}

describe('MissionComposer dictation', () => {
  it('adds the dictated words after the typed mission', async () => {
    const onChange = renderComposer('Research our competitors', false);

    await userEvent.click(screen.getByRole('button', { name: 'Dictate your mission' }));

    expect(onChange).toHaveBeenCalledWith('Research our competitors then a reviewer checks it');
  });

  it('dictates a change request once there is a team', async () => {
    const onChange = renderComposer('', true);

    await userEvent.click(screen.getByRole('button', { name: 'Dictate a change to your team' }));

    expect(onChange).toHaveBeenCalledWith('then a reviewer checks it');
  });
});
