import { renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useJump } from './jump';

const motion = vi.hoisted(() => ({ reduced: false }));

vi.mock('motion/react', async (importOriginal) => ({
  ...(await importOriginal<typeof import('motion/react')>()),
  useReducedMotion: () => motion.reduced,
}));

function place(id: string, tag = 'h3'): HTMLElement {
  const element = document.createElement(tag);
  element.id = id;
  element.tabIndex = -1;
  element.scrollIntoView = vi.fn();
  document.body.append(element);
  return element;
}

afterEach(() => {
  document.body.replaceChildren();
  motion.reduced = false;
});

describe('useJump', () => {
  it('scrolls the target to the top smoothly, then focuses it without scrolling again', () => {
    const target = place('run-7-deliverable-2');
    const focus = vi.spyOn(target, 'focus');
    const { result } = renderHook(() => useJump());

    result.current('run-7-deliverable-2');

    expect(target.scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' });
    expect(focus).toHaveBeenCalledWith({ preventScroll: true });
    expect(document.activeElement).toBe(target);
  });

  it('focuses another element when asked, e.g. the heading inside the target', () => {
    const target = place('run-7-deliverable-2', 'article');
    const heading = place('run-7-deliverable-2-title');
    const { result } = renderHook(() => useJump());

    result.current('run-7-deliverable-2', 'run-7-deliverable-2-title', 'nearest');

    expect(target.scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'nearest' });
    expect(document.activeElement).toBe(heading);
  });

  it('jumps without smooth scrolling when the person asked for reduced motion', () => {
    motion.reduced = true;
    const target = place('approval-31');
    const { result } = renderHook(() => useJump());

    result.current('approval-31');

    expect(target.scrollIntoView).toHaveBeenCalledWith({ behavior: 'auto', block: 'start' });
  });

  it('does nothing when the target is not there', () => {
    const { result } = renderHook(() => useJump());
    expect(() => result.current('missing')).not.toThrow();
  });
});
