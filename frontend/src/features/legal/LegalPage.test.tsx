import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { LEGAL_LINKS, type LegalPath } from '../../core/routes';
import { LegalPage } from './LegalPage';

/** The page as the app routes it, reached at `address`. */
function renderAt(path: LegalPath, address: string = path) {
  render(
    <MemoryRouter initialEntries={[address]}>
      <Routes>
        <Route path={path} element={<LegalPage path={path} />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('LegalPage', () => {
  it.each([
    ['/legal', 'Mentions légales'],
    ['/privacy', 'Politique de confidentialité'],
    ['/terms', "Conditions générales d'utilisation"],
  ] as const)('%s shows its document, in French', (path, title) => {
    renderAt(path);

    const heading = screen.getByRole('heading', { level: 1, name: title });
    expect(heading.closest('article')).toHaveAttribute('lang', 'fr');
  });

  it.each(['/privacy/', '/PRIVACY'])('shows the privacy policy at %s too', (address) => {
    renderAt('/privacy', address);

    expect(
      screen.getByRole('heading', { level: 1, name: 'Politique de confidentialité' }),
    ).toBeInTheDocument();
  });

  it('links every legal page from every legal page', () => {
    renderAt('/privacy');

    const nav = screen.getByRole('navigation', { name: 'Legal' });
    const links = Array.from(nav.querySelectorAll('a')).map((link) => link.getAttribute('href'));
    expect(links).toEqual(LEGAL_LINKS.map((link) => link.path));
  });

  it('says it is a draft while operator facts are missing, and marks each one', () => {
    renderAt('/legal');

    expect(screen.getByRole('note')).toHaveTextContent('Version provisoire');
    expect(screen.getAllByText(/\[à compléter : /).length).toBeGreaterThan(0);
  });

  it('describes the only cookie and storage the app uses', () => {
    renderAt('/privacy');

    expect(screen.getByText('aimix_refresh')).toBeInTheDocument();
    expect(screen.getByText('aimix.mission.v1.*')).toBeInTheDocument();
  });
});
