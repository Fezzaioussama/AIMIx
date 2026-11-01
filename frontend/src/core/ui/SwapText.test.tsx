import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { SwapText } from './SwapText';

const motion = vi.hoisted(() => ({ reduced: false }));

vi.mock('motion/react', async (original) => ({
  ...(await original<typeof import('motion/react')>()),
  useReducedMotion: () => motion.reduced,
}));

afterEach(() => {
  motion.reduced = false;
});

/** The words that are leaving, partway through their exit. */
async function leaving(text: string): Promise<HTMLElement> {
  const old = screen.getByText(text);
  await waitFor(() => expect(Number(old.style.opacity)).toBeLessThan(1));
  return old;
}

describe('SwapText', () => {
  it('shows its text on first render without animating it in', () => {
    render(<SwapText text="Your team is working" className="text-white" />);

    const words = screen.getByText('Your team is working');
    expect(words).toHaveClass('inline-block', 'text-white');
    expect(words.style.opacity).not.toBe('0');
    expect(words.style.transform).not.toMatch(/translate/);
  });

  it('swaps to the new text, the old words rising out through a blur', async () => {
    const { rerender } = render(<SwapText text="Being written" />);

    rerender(<SwapText text="Ready" />);

    const old = await leaving('Being written');
    expect(old.style.transform).toMatch(/translateY\(-/);
    expect(old.style.filter).toMatch(/blur/);
    expect(await screen.findByText('Ready')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText('Being written')).not.toBeInTheDocument());
  });

  it('only cross-fades under reduced motion', async () => {
    motion.reduced = true;
    const { rerender } = render(<SwapText text="Being written" />);

    rerender(<SwapText text="Ready" />);

    const old = await leaving('Being written');
    expect(old.style.transform).toBe('');
    expect(old.style.filter).toBe('');
    expect(await screen.findByText('Ready')).toBeInTheDocument();
  });
});
