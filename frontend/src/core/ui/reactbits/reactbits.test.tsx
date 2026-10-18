import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { Aurora } from './Aurora';
import { BlurText } from './BlurText';
import { ClickSpark } from './ClickSpark';
import { CountUp } from './CountUp';
import { RotatingText } from './RotatingText';
import { SpotlightCard } from './SpotlightCard';

describe('React Bits adaptations', () => {
  it('Aurora degrades to an empty decorative layer without WebGL2', () => {
    const { container } = render(<Aurora className="inset-0" />);
    const layer = container.firstElementChild;
    expect(layer).toHaveAttribute('aria-hidden', 'true');
    expect(layer?.querySelector('canvas')).toBeNull();
  });

  it('BlurText gives assistive tech the plain text once', () => {
    render(
      <h1>
        <BlurText text="Welcome back" />
      </h1>,
    );
    expect(screen.getByRole('heading', { name: 'Welcome back' })).toBeInTheDocument();
  });

  it('RotatingText exposes every phrase instead of announcing each change', () => {
    render(<RotatingText texts={['agents', 'pipelines']} />);
    expect(screen.getByText('agents, pipelines')).toHaveClass('sr-only');
  });

  it('CountUp settles on its target value', async () => {
    const { container } = render(<CountUp to={42} duration={0.05} />);
    await waitFor(() => expect(container.textContent).toBe('42'));
  });

  it('ClickSpark passes clicks through when no canvas context exists', async () => {
    const onClick = vi.fn();
    render(
      <ClickSpark>
        <button type="button" onClick={onClick}>
          Run
        </button>
      </ClickSpark>,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Run' }));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it('SpotlightCard tracks the pointer through CSS variables', () => {
    render(
      <SpotlightCard as="section" aria-label="Card">
        content
      </SpotlightCard>,
    );
    const card = screen.getByRole('region', { name: 'Card' });
    card.dispatchEvent(new MouseEvent('pointermove', { bubbles: true, clientX: 30, clientY: 12 }));
    expect(card.style.getPropertyValue('--spot-x')).toBe('30px');
    expect(card.style.getPropertyValue('--spot-y')).toBe('12px');
  });
});
