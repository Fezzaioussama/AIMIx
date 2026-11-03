import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { SPOKEN } from '../../core/voice/speakingMic';
import { ChatComposer } from './ChatComposer';

vi.mock('../../core/voice/MicButton', () => import('../../core/voice/speakingMic'));

function renderComposer(value: string) {
  const onChange = vi.fn();
  const onSend = vi.fn();
  render(<ChatComposer value={value} disabled={false} onChange={onChange} onSend={onSend} />);
  return { onChange, onSend };
}

describe('ChatComposer dictation', () => {
  it('puts what was said in the box, to read before sending', async () => {
    const { onChange, onSend } = renderComposer('');

    await userEvent.click(screen.getByRole('button', { name: 'Dictate your message' }));

    expect(onChange).toHaveBeenCalledWith(SPOKEN);
    expect(onSend).not.toHaveBeenCalled();
  });

  it('adds what was said after what is typed', async () => {
    const { onChange } = renderComposer('Build a workflow for my weekly specials');

    await userEvent.click(screen.getByRole('button', { name: 'Dictate your message' }));

    expect(onChange).toHaveBeenCalledWith(`Build a workflow for my weekly specials ${SPOKEN}`);
  });
});
