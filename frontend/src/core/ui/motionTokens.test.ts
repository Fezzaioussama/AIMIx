import { describe, expect, it } from 'vitest';

import styles from '../../styles.css?raw';
import { EASE_SMOOTH_OUT } from './motionTokens';

describe('motionTokens', () => {
  it('eases motion/react and CSS transitions along the same curve', () => {
    expect(styles).toContain(`--ease-smooth-out: cubic-bezier(${EASE_SMOOTH_OUT.join(', ')});`);
  });
});
