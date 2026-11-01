import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { chosenFiles } from './chosenFiles';

describe('chosenFiles', () => {
  it('gives the files chosen, and takes the same one again', async () => {
    const user = userEvent.setup();
    const onFiles = vi.fn();
    render(
      <input type="file" aria-label="Pick" onChange={(event) => onFiles(chosenFiles(event))} />,
    );
    const file = new File(['%PDF'], 'report.pdf', { type: 'application/pdf' });

    await user.upload(screen.getByLabelText('Pick'), file);
    await user.upload(screen.getByLabelText('Pick'), file);

    expect(onFiles).toHaveBeenCalledTimes(2);
    expect(onFiles).toHaveBeenLastCalledWith([file]);
    expect(screen.getByLabelText('Pick')).toHaveValue('');
  });
});
