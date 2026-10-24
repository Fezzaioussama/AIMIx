import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { GlowLink } from './GlowLink';

describe('GlowLink', () => {
  it('is a real link, so it can be opened in a new tab', () => {
    render(
      <MemoryRouter>
        <GlowLink to="/register">Get started</GlowLink>
      </MemoryRouter>,
    );
    expect(screen.getByRole('link', { name: 'Get started' })).toHaveAttribute('href', '/register');
  });
});
