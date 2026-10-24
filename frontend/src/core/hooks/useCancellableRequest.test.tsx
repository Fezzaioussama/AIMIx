import { renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { useCancellableRequest } from './useCancellableRequest';

describe('useCancellableRequest', () => {
  it('aborts the previous request when a new one starts', () => {
    const { result } = renderHook(() => useCancellableRequest());

    const first = result.current.start();
    const second = result.current.start();

    expect(first.signal.aborted).toBe(true);
    expect(second.signal.aborted).toBe(false);
    expect(result.current.finish(first)).toBe(false);
    expect(result.current.finish(second)).toBe(true);
    // Finishing lets the request go, so it only counts once.
    expect(result.current.finish(second)).toBe(false);
  });

  it('cancels the current request, which still finishes as the current one', () => {
    const { result } = renderHook(() => useCancellableRequest());
    const request = result.current.start();

    result.current.cancel();

    expect(request.signal.aborted).toBe(true);
    expect(result.current.finish(request)).toBe(true);
  });

  it('aborts on unmount, after which nothing finishes', () => {
    const { result, unmount } = renderHook(() => useCancellableRequest());
    const request = result.current.start();

    unmount();

    expect(request.signal.aborted).toBe(true);
    expect(result.current.finish(request)).toBe(false);
  });

  it('keeps the same functions across renders', () => {
    const { result, rerender } = renderHook(() => useCancellableRequest());
    const first = result.current;

    rerender();

    expect(result.current.start).toBe(first.start);
    expect(result.current.cancel).toBe(first.cancel);
    expect(result.current.finish).toBe(first.finish);
  });
});
