import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { AttachWebPage } from './AttachWebPage';

const toggle = () => screen.getByRole('button', { name: 'Add a web page' });
const link = () => screen.getByRole('textbox', { name: 'Link to a web page' });
const read = () => screen.getByRole('button', { name: 'Read page' });

describe('AttachWebPage', () => {
  it('opens a field for a link, and reads the page on Enter', async () => {
    const user = userEvent.setup();
    const onRead = vi.fn();
    render(<AttachWebPage onRead={onRead} />);
    expect(toggle()).toHaveAttribute('aria-expanded', 'false');

    await user.click(toggle());

    expect(toggle()).toHaveAttribute('aria-expanded', 'true');
    expect(link()).toHaveFocus();
    expect(link()).toHaveAttribute('type', 'url');
    expect(link()).toHaveAttribute('placeholder', 'Paste a link (https://…)');

    await user.type(link(), 'example.com/a{Enter}');

    expect(onRead).toHaveBeenCalledWith('https://example.com/a');
    // Done with the field: it closes, and focus goes back to what opened it.
    expect(toggle()).toHaveAttribute('aria-expanded', 'false');
    expect(toggle()).toHaveFocus();
  });

  it('closes on Escape, gives focus back and reads nothing', async () => {
    const user = userEvent.setup();
    const onRead = vi.fn();
    render(<AttachWebPage onRead={onRead} />);
    await user.click(toggle());
    await user.type(link(), 'example.com');

    await user.keyboard('{Escape}');

    expect(toggle()).toHaveAttribute('aria-expanded', 'false');
    expect(toggle()).toHaveFocus();
    expect(onRead).not.toHaveBeenCalled();
  });

  it('waits for something that can be a web address', async () => {
    const user = userEvent.setup();
    const onRead = vi.fn();
    render(<AttachWebPage onRead={onRead} />);
    await user.click(toggle());

    expect(read()).toBeDisabled();
    await user.type(link(), 'not a link{Enter}');
    expect(read()).toBeDisabled();
    expect(onRead).not.toHaveBeenCalled();
  });

  it('reads nothing while another document is being read', async () => {
    const user = userEvent.setup();
    const onRead = vi.fn();
    render(<AttachWebPage onRead={onRead} busy />);

    await user.click(toggle());
    await user.type(link(), 'example.com{Enter}');

    expect(read()).toBeDisabled();
    expect(onRead).not.toHaveBeenCalled();
  });

  it('closes the field while the form is busy', async () => {
    const user = userEvent.setup();
    const { rerender } = render(<AttachWebPage onRead={vi.fn()} />);
    await user.click(toggle());
    expect(link()).toBeInTheDocument();

    rerender(<AttachWebPage onRead={vi.fn()} disabled />);

    expect(toggle()).toBeDisabled();
    expect(screen.queryByRole('textbox', { name: 'Link to a web page' })).not.toBeInTheDocument();
  });

  it('keeps the closed field out of reach', () => {
    render(<AttachWebPage onRead={vi.fn()} />);
    expect(screen.queryByRole('textbox', { name: 'Link to a web page' })).not.toBeInTheDocument();
  });
});
