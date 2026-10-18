import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { ChatPage } from './ChatPage';

describe('ChatPage', () => {
  it('fills and focuses the composer when a starter prompt is picked', async () => {
    render(<ChatPage />);
    await userEvent.click(screen.getByRole('button', { name: /Draft an email/ }));
    const composer = screen.getByPlaceholderText('Ask anything…');
    expect(composer).toHaveValue(
      'Draft a short, friendly email announcing a product launch to our customers.',
    );
    expect(composer).toHaveFocus();
    expect(screen.getByRole('button', { name: 'Send message' })).toBeEnabled();
  });
});
