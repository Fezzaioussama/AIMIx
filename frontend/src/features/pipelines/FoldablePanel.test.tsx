import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { DisclosureButton, Foldable, PanelToggle } from './FoldablePanel';

function Panel({ summary }: { summary?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <PanelToggle
        id="team-work"
        level={3}
        icon={null}
        title="How your team got there"
        summary={summary}
        open={open}
        onToggle={() => setOpen((was) => !was)}
      />
      <Foldable id="team-work-body" open={open}>
        <p>What each agent did</p>
      </Foldable>
    </>
  );
}

describe('PanelToggle and Foldable', () => {
  it('opens and closes the panel it names, with its summary in the button', async () => {
    render(<Panel summary="4 agents · 3 stages" />);
    const toggle = screen.getByRole('button', {
      name: 'How your team got there, 4 agents · 3 stages',
    });
    const body = document.getElementById('team-work-body');

    expect(screen.getByRole('heading', { level: 3 })).toContainElement(toggle);
    expect(toggle).toHaveAttribute('aria-controls', 'team-work-body');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(body).toHaveAttribute('inert');

    await userEvent.click(toggle);

    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(body).not.toHaveAttribute('inert');
    expect(body).toHaveClass('grid-rows-[1fr]');
  });

  it('shows no summary when none is given', () => {
    render(<Panel />);

    expect(screen.getByRole('button', { name: 'How your team got there' })).toBeInTheDocument();
  });

  it('times a large fold slower than a small one, and closes faster than it opens', () => {
    const { rerender } = render(
      <Foldable id="fold" open={true}>
        x
      </Foldable>,
    );
    const fold = document.getElementById('fold');
    expect(fold).toHaveClass('duration-350', 'ease-smooth-out', 'motion-reduce:transition-none');

    rerender(
      <Foldable id="fold" open={false}>
        x
      </Foldable>,
    );
    expect(fold).toHaveClass('duration-250');

    rerender(
      <Foldable id="fold" open={true} size="small">
        x
      </Foldable>,
    );
    expect(fold).toHaveClass('duration-250');

    rerender(
      <Foldable id="fold" open={false} size="small">
        x
      </Foldable>,
    );
    expect(fold).toHaveClass('duration-150');
  });

  it('pads its body like a panel unless told otherwise', () => {
    const { rerender } = render(
      <Foldable id="fold" open={true}>
        <span>inside</span>
      </Foldable>,
    );
    expect(screen.getByText('inside').parentElement).toHaveClass('px-4', 'pb-5');

    rerender(
      <Foldable id="fold" open={true} bodyClassName="pt-3">
        <span>inside</span>
      </Foldable>,
    );
    expect(screen.getByText('inside').parentElement).toHaveClass('pt-3');
    expect(screen.getByText('inside').parentElement).not.toHaveClass('px-4');
  });
});

describe('DisclosureButton', () => {
  it('says what it opens and whether it is open', async () => {
    const onToggle = vi.fn();
    const { rerender } = render(
      <DisclosureButton
        open={false}
        controls="check"
        label="Read the full check"
        onToggle={onToggle}
      />,
    );
    const button = screen.getByRole('button', { name: 'Read the full check' });

    expect(button).toHaveAttribute('aria-expanded', 'false');
    expect(button).toHaveAttribute('aria-controls', 'check');
    await userEvent.click(button);
    expect(onToggle).toHaveBeenCalledOnce();

    rerender(
      <DisclosureButton
        open={true}
        controls="check"
        label="Hide the full check"
        onToggle={onToggle}
      />,
    );
    expect(screen.getByRole('button', { name: 'Hide the full check' })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
  });

  it('carries its own id, so a "Hide" button at the end of its panel can focus it again', () => {
    render(
      <DisclosureButton
        id="check-toggle"
        open={true}
        controls="check"
        label="Hide the full check"
        onToggle={() => {}}
      />,
    );

    document.getElementById('check-toggle')?.focus();

    expect(screen.getByRole('button', { name: 'Hide the full check' })).toHaveFocus();
  });
});
