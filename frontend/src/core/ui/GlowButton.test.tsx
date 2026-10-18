import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { GlowButton } from './GlowButton';

describe('GlowButton', () => {
  it('is a plain, labelled button when idle', () => {
    render(<GlowButton>Run Pipeline</GlowButton>);
    const button = screen.getByRole('button', { name: 'Run Pipeline' });
    expect(button).toBeEnabled();
    expect(button).toHaveAttribute('type', 'button');
  });

  it('blocks clicks while busy without adding the spinner to its name', () => {
    render(<GlowButton busy>Saving…</GlowButton>);
    expect(screen.getByRole('button', { name: 'Saving…' })).toBeDisabled();
    expect(screen.queryByRole('status')).toBeNull();
  });
});
