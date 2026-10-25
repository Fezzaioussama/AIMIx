import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { useMediaQuery } from './useMediaQuery';

/** A window whose media query answer the test controls, and the listeners watching it. */
function stubMedia(initial: boolean) {
  const listeners = new Set<() => void>();
  let matches = initial;
  window.matchMedia = ((query: string) => ({
    get matches() {
      return matches;
    },
    media: query,
    addEventListener: (_type: string, listener: () => void) => listeners.add(listener),
    removeEventListener: (_type: string, listener: () => void) => listeners.delete(listener),
  })) as unknown as typeof window.matchMedia;
  return {
    listeners,
    answer(value: boolean) {
      matches = value;
      listeners.forEach((listener) => listener());
    },
  };
}

describe('useMediaQuery', () => {
  afterEach(() => Reflect.deleteProperty(window, 'matchMedia'));

  it('is false where the browser cannot answer', () => {
    const { result } = renderHook(() => useMediaQuery('(min-width: 1280px)'));

    expect(result.current).toBe(false);
  });

  it('follows the query as the window changes, and stops listening when unmounted', () => {
    const media = stubMedia(true);
    const { result, unmount } = renderHook(() => useMediaQuery('(min-width: 1280px)'));
    expect(result.current).toBe(true);
    expect(media.listeners.size).toBe(1);

    act(() => media.answer(false));
    expect(result.current).toBe(false);
    act(() => media.answer(true));
    expect(result.current).toBe(true);

    unmount();
    expect(media.listeners.size).toBe(0);
  });
});
