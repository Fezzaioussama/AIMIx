import { afterEach, describe, expect, it, vi } from 'vitest';

import { hasWebGL } from './webgl';

describe('hasWebGL', () => {
  afterEach(() => vi.restoreAllMocks());

  it('is false where the browser gives no WebGL context', () => {
    // test-setup.ts models a browser without any canvas backend.
    expect(hasWebGL()).toBe(false);
  });

  it('is true when a context can be created, and releases the probe context', () => {
    const loseContext = vi.fn();
    const context = { getExtension: () => ({ loseContext }) };
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(
      context as unknown as RenderingContext,
    );
    expect(hasWebGL()).toBe(true);
    expect(loseContext).toHaveBeenCalledOnce();
  });

  it('is false if probing throws', () => {
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(hasWebGL()).toBe(false);
  });
});
