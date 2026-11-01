import { render, screen } from '@testing-library/react';
import { createRef } from 'react';
import { describe, expect, it } from 'vitest';

import { Heading, type HeadingLevel } from './Heading';

describe('Heading', () => {
  it.each<HeadingLevel>([2, 3, 4, 5, 6])('renders an h%i', (level) => {
    render(<Heading level={level}>Saved during this run</Heading>);

    expect(screen.getByRole('heading', { level, name: 'Saved during this run' })).toBeVisible();
  });

  it('passes its attributes and ref to the heading', () => {
    const ref = createRef<HTMLHeadingElement>();
    render(
      <Heading level={3} id="run-7-outcome" tabIndex={-1} className="text-xl" ref={ref}>
        2 deliverables ready
      </Heading>,
    );

    const heading = screen.getByRole('heading', { level: 3 });
    expect(heading).toHaveAttribute('id', 'run-7-outcome');
    expect(heading).toHaveAttribute('tabindex', '-1');
    expect(heading).toHaveClass('text-xl');
    expect(ref.current).toBe(heading);
  });
});
