import { useEffect, useRef, type RefObject } from 'react';

/**
 * A ref that always holds the latest `value`, for async work that must read the current
 * one when it finishes rather than the one it started with.
 */
export function useLatest<T>(value: T): RefObject<T> {
  const ref = useRef(value);
  useEffect(() => {
    ref.current = value;
  });
  return ref;
}
