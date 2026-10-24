import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { STEP_INTERVAL_MS, useStepCarousel } from './useStepCarousel';

describe('useStepCarousel', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('advances on its own and wraps around', () => {
    const { result } = renderHook(() => useStepCarousel(3));
    expect(result.current.active).toBe(0);
    act(() => vi.advanceTimersByTime(STEP_INTERVAL_MS));
    expect(result.current.active).toBe(1);
    // One tick per act: the next timer is armed only after React re-renders.
    act(() => vi.advanceTimersByTime(STEP_INTERVAL_MS));
    expect(result.current.active).toBe(2);
    act(() => vi.advanceTimersByTime(STEP_INTERVAL_MS));
    expect(result.current.active).toBe(0);
  });

  it('stops for good once the visitor picks a step', () => {
    const { result } = renderHook(() => useStepCarousel(3));
    act(() => result.current.select(2));
    expect(result.current.active).toBe(2);
    expect(result.current.auto).toBe(false);
    act(() => vi.advanceTimersByTime(STEP_INTERVAL_MS * 3));
    expect(result.current.active).toBe(2);
  });

  it('pauses while held and resumes when released', () => {
    const { result } = renderHook(() => useStepCarousel(3));
    act(() => result.current.hold(true));
    act(() => vi.advanceTimersByTime(STEP_INTERVAL_MS * 2));
    expect(result.current.active).toBe(0);
    act(() => result.current.hold(false));
    act(() => vi.advanceTimersByTime(STEP_INTERVAL_MS));
    expect(result.current.active).toBe(1);
  });
});
