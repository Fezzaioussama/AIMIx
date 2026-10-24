import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { PipelineInput } from '../../core/api/types';
import { PipelineInputsEditor } from './PipelineInputsEditor';

function Harness() {
  const [inputs, setInputs] = useState<PipelineInput[]>([]);
  return (
    <>
      <PipelineInputsEditor inputs={inputs} onChange={setInputs} />
      <output data-testid="inputs">{JSON.stringify(inputs)}</output>
    </>
  );
}

describe('PipelineInputsEditor', () => {
  it('adds, names, labels and removes run inputs', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    expect(screen.getByText(/No named inputs/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '+ Add input' }));
    const name = screen.getByRole('textbox', { name: 'Name of input 1' });
    await user.clear(name);
    await user.type(name, 'Target Audience');
    await user.type(screen.getByRole('textbox', { name: 'Label of input 1' }), 'Audience');

    expect(screen.getByTestId('inputs')).toHaveTextContent(
      '[{"name":"target_audience","label":"Audience","description":""}]',
    );

    await user.click(screen.getByRole('button', { name: 'Remove input 1' }));
    expect(screen.getByTestId('inputs')).toHaveTextContent('[]');
  });

  it('explains a name that cannot be saved', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole('button', { name: '+ Add input' }));
    const name = screen.getByRole('textbox', { name: 'Name of input 1' });

    await user.clear(name);
    await user.type(name, 'input');

    expect(name).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText(/reserved for the stage input/)).toBeInTheDocument();
  });
});
