import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ToggleSwitch } from './ToggleSwitch';

describe('ToggleSwitch', () => {
  it('says its state in words and asks for the opposite when pressed', async () => {
    const onChange = vi.fn();
    const { rerender } = render(<ToggleSwitch checked label="Run it weekly" onChange={onChange} />);
    const toggle = screen.getByRole('switch', { name: 'Run it weekly' });
    expect(toggle).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByText('On')).toBeInTheDocument();

    await userEvent.click(toggle);
    expect(onChange).toHaveBeenLastCalledWith(false);

    rerender(<ToggleSwitch checked={false} label="Run it weekly" onChange={onChange} />);
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    expect(screen.getByText('Off')).toBeInTheDocument();
    await userEvent.click(toggle);
    expect(onChange).toHaveBeenLastCalledWith(true);
  });

  it('can be pressed with the keyboard and disabled', async () => {
    const onChange = vi.fn();
    const { rerender } = render(<ToggleSwitch checked label="Run it" onChange={onChange} />);

    await userEvent.tab();
    await userEvent.keyboard('{Enter}');
    expect(onChange).toHaveBeenCalledTimes(1);

    rerender(<ToggleSwitch checked label="Run it" disabled onChange={onChange} />);
    expect(screen.getByRole('switch')).toBeDisabled();
  });
});
