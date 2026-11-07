import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { makeRun } from '../testData';
import { FeedbackRow } from './FeedbackRow';
import { controls } from './testReport';

const ended = makeRun({ status: 'succeeded', finished_at: '2026-10-24T10:00:09Z' });

describe('FeedbackRow', () => {
  it('shows nothing while the run works', () => {
    const { container } = render(<FeedbackRow run={makeRun()} control={controls()} level={3} />);

    expect(container).toBeEmptyDOMElement();
  });

  it('rates the run with a thumb, and takes the thumb back', async () => {
    const control = controls();
    const { rerender } = render(<FeedbackRow run={ended} control={control} level={3} />);
    const rating = screen.getByRole('group', { name: 'Your rating' });

    await userEvent.click(within(rating).getByRole('button', { name: 'Useful' }));
    rerender(<FeedbackRow run={{ ...ended, rating: 1 }} control={control} level={3} />);
    const useful = within(rating).getByRole('button', { name: 'Useful' });
    expect(useful).toHaveAttribute('aria-pressed', 'true');
    await userEvent.click(useful);

    expect(control.rate).toHaveBeenNthCalledWith(1, { rating: 1, feedback: '' });
    expect(control.rate).toHaveBeenNthCalledWith(2, { rating: null, feedback: '' });
  });

  it('saves a note with the rating the run has, and says so', async () => {
    const control = controls();
    const rated = { ...ended, rating: -1 as const };
    const { rerender } = render(<FeedbackRow run={rated} control={control} level={3} />);
    const save = screen.getByRole('button', { name: 'Save note' });
    expect(save).toBeDisabled();

    await userEvent.type(screen.getByLabelText(/What should the next team/), ' Too long. ');
    await userEvent.click(save);
    rerender(<FeedbackRow run={{ ...rated, feedback: 'Too long.' }} control={control} level={3} />);

    expect(control.rate).toHaveBeenCalledWith({ rating: -1, feedback: 'Too long.' });
    expect(screen.getByText('Saved. The next team you plan will know.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save note' })).toBeDisabled();
  });
});
