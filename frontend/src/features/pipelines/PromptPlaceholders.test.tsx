import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { PromptPlaceholders } from './PromptPlaceholders';

describe('PromptPlaceholders', () => {
  it('offers the declared inputs and warns about one nothing fills', () => {
    render(
      <PromptPlaceholders
        prompt="Write about {topic} for {audeince}"
        inputs={[
          { name: 'topic', label: 'Topic', description: '' },
          { name: 'audience', label: '', description: '' },
        ]}
      />,
    );
    expect(screen.getByText('{audience}')).toBeInTheDocument();
    expect(screen.getByText(/Not an input, left as written: \{audeince\}/)).toBeInTheDocument();
  });

  it('stays quiet when every placeholder is filled', () => {
    render(<PromptPlaceholders prompt="Summarise {input}" inputs={[]} />);
    expect(screen.queryByText(/Not an input/)).not.toBeInTheDocument();
  });
});
