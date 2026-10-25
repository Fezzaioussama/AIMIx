import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { describeCost } from '../usageFormat';
import { CostText } from './CostText';

const view = describeCost({
  input_tokens: 1234,
  output_tokens: 567,
  cost_usd: 0.0123,
  cost_complete: true,
});
const unknown = describeCost({
  input_tokens: 1234,
  output_tokens: 567,
  cost_usd: null,
  cost_complete: false,
});

describe('CostText', () => {
  it('shows the cost, with the token counts as its tooltip', () => {
    if (!view) throw new Error('a used run has a cost view');
    render(<CostText view={view} />);

    expect(screen.getByText('$0.0123')).toHaveAttribute('title', '1,234 tokens in, 567 out');
  });

  it('reads the token counts out too, so nothing depends on the pointer', () => {
    if (!view) throw new Error('a used run has a cost view');
    const { container } = render(<CostText view={view} />);

    expect(container).toHaveTextContent('$0.0123 (1,234 tokens in, 567 out)');
  });

  it('says the cost is unknown for the model, and still has the tokens', () => {
    if (!unknown) throw new Error('used tokens have a cost view');
    render(<CostText view={unknown} />);

    expect(screen.getByText('Cost unknown for this model')).toHaveAttribute(
      'title',
      '1,234 tokens in, 567 out',
    );
  });

  it('can use the short words in a tight row', () => {
    if (!unknown) throw new Error('used tokens have a cost view');
    render(<CostText view={unknown} compact />);

    expect(screen.getByText('Cost unknown')).toBeInTheDocument();
    expect(screen.queryByText('Cost unknown for this model')).not.toBeInTheDocument();
  });
});
