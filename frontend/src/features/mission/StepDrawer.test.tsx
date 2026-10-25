import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { StepDrawer } from './StepDrawer';
import { PLAN, TOOLS } from './testData';

const [researcher, analyst] = PLAN.steps;

function drawer(overrides: Partial<Parameters<typeof StepDrawer>[0]> = {}) {
  const handlers = { onChange: vi.fn(), onRemove: vi.fn(), onClose: vi.fn() };
  const view = render(
    <StepDrawer
      step={researcher}
      steps={PLAN.steps}
      inputs={PLAN.inputs}
      models={['vendor/fast', 'vendor/smart']}
      tools={TOOLS}
      canRemove
      {...handlers}
      {...overrides}
    />,
  );
  return { ...handlers, ...view };
}

describe('StepDrawer', () => {
  it('is a dialog named by the agent, and takes focus when it opens', () => {
    drawer();

    const dialog = screen.getByRole('dialog', { name: 'Researcher' });

    expect(dialog).toHaveAttribute('aria-modal', 'false');
    expect(screen.getByRole('heading', { name: 'Researcher' })).toHaveFocus();
  });

  it('names an agent without a role by its title', () => {
    drawer({ step: { ...researcher, role: '' } });

    expect(screen.getByRole('dialog', { name: 'Market research' })).toBeInTheDocument();
  });

  it('edits the role, the model and the prompt through labelled fields', async () => {
    const user = userEvent.setup();
    const { onChange } = drawer();

    await user.type(screen.getByLabelText('Agent role'), '!');
    await user.selectOptions(screen.getByLabelText('Model'), 'vendor/smart');
    await user.type(screen.getByLabelText('Prompt'), '?');

    expect(onChange).toHaveBeenCalledWith({ role: 'Researcher!' });
    expect(onChange).toHaveBeenCalledWith({ model: 'vendor/smart' });
    expect(onChange).toHaveBeenCalledWith({ prompt: `${researcher.prompt}?` });
  });

  it('offers the agent’s tools', async () => {
    const user = userEvent.setup();
    const { onChange } = drawer({ step: analyst });

    await user.click(screen.getByRole('button', { name: 'No tools' }));

    expect(onChange).toHaveBeenCalledWith({ allowed_tools: [] });
  });

  it('closes with the button and with Escape', async () => {
    const user = userEvent.setup();
    const { onClose } = drawer();

    await user.click(screen.getByRole('button', { name: 'Close' }));
    await user.keyboard('{Escape}');

    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it('removes the agent unless it is the last one', async () => {
    const user = userEvent.setup();
    const { onRemove, rerender, onChange, onClose } = drawer();
    await user.click(screen.getByRole('button', { name: 'Remove step 1' }));
    expect(onRemove).toHaveBeenCalledTimes(1);

    rerender(
      <StepDrawer
        step={researcher}
        steps={PLAN.steps}
        inputs={PLAN.inputs}
        models={['vendor/fast']}
        tools={TOOLS}
        canRemove={false}
        onChange={onChange}
        onRemove={onRemove}
        onClose={onClose}
      />,
    );

    expect(screen.getByRole('button', { name: 'Remove step 1' })).toBeDisabled();
  });

  it('says when the models or tools could not be loaded', () => {
    drawer({ notice: 'Could not load models.' });

    expect(screen.getByText('Could not load models.')).toBeInTheDocument();
  });

  it('moves focus to the heading again when another agent is picked', () => {
    const { rerender, onChange, onRemove, onClose } = drawer();
    screen.getByLabelText('Prompt').focus();

    rerender(
      <StepDrawer
        step={analyst}
        steps={PLAN.steps}
        inputs={PLAN.inputs}
        models={['vendor/fast']}
        tools={TOOLS}
        canRemove
        onChange={onChange}
        onRemove={onRemove}
        onClose={onClose}
      />,
    );

    expect(screen.getByRole('heading', { name: 'Analyst' })).toHaveFocus();
  });
});
