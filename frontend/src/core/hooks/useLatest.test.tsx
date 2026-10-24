import { renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { useLatest } from './useLatest';

describe('useLatest', () => {
  it('is one ref that always holds the latest value', () => {
    const { result, rerender } = renderHook(({ value }) => useLatest(value), {
      initialProps: { value: 'first' },
    });
    const ref = result.current;

    rerender({ value: 'second' });

    expect(result.current).toBe(ref);
    expect(ref.current).toBe('second');
  });
});
