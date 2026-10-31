import { describe, expect, it } from 'vitest';

import { appendDictation } from './dictation';

describe('appendDictation', () => {
  it('fills an empty box with the words', () => {
    expect(appendDictation('  ', 'Plan a launch')).toBe('Plan a launch');
  });

  it('adds the words after what is typed, with one space', () => {
    expect(appendDictation('Plan a launch ', 'with three posts')).toBe(
      'Plan a launch with three posts',
    );
  });

  it('stops at the box limit', () => {
    expect(appendDictation('abc', 'defgh', 6)).toBe('abc de');
  });
});
