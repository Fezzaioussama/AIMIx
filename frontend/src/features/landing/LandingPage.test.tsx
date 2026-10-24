import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it } from 'vitest';

import { AuthProvider } from '../../core/auth/AuthContext';
import { clearTokens, saveTokens } from '../../core/auth/tokenStorage';
import { NAV_LINKS, RELEASE_STAGE } from './content/site';
import { LandingPage } from './LandingPage';

function renderLanding() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <LandingPage />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('LandingPage', () => {
  afterEach(() => clearTokens());

  it('leads with the product promise', () => {
    renderLanding();
    expect(
      screen.getByRole('heading', {
        level: 1,
        name: 'Design, coordinate, and run multi-agent workflows',
      }),
    ).toBeInTheDocument();
  });

  it('points a visitor at registration and sign-in', () => {
    renderLanding();
    for (const link of screen.getAllByRole('link', { name: /get started/i })) {
      expect(link).toHaveAttribute('href', '/register');
    }
    expect(screen.getAllByRole('link', { name: 'Sign in' })[0]).toHaveAttribute('href', '/login');
  });

  it('sends a signed-in user straight into the app instead', () => {
    saveTokens({ access: 'token', refresh: 'refresh' });
    renderLanding();
    expect(screen.queryByRole('link', { name: /get started/i })).toBeNull();
    for (const link of screen.getAllByRole('link', { name: /open the app/i })) {
      expect(link).toHaveAttribute('href', '/chat');
    }
  });

  it('has a section for every anchor the navigation points at', () => {
    renderLanding();
    for (const link of NAV_LINKS) {
      expect(document.getElementById(link.href.slice(1)), link.href).not.toBeNull();
    }
  });

  it('labels this release in the nav and footer, but not in the hero', () => {
    renderLanding();
    const label = new RegExp(RELEASE_STAGE, 'i');
    expect(within(screen.getByRole('banner')).getByText(label)).toBeInTheDocument();
    expect(within(screen.getByRole('contentinfo')).getByText(label)).toBeInTheDocument();
    const hero = screen.getByRole('heading', { level: 1 }).closest('section') as HTMLElement;
    expect(within(hero).queryByText(label)).toBeNull();
  });

  it('keeps "Sign in" in the top bar at every width, never hidden', () => {
    renderLanding();
    const bar = screen.getByRole('navigation', { name: 'Primary' });
    const link = within(bar).getByRole('link', { name: 'Sign in' });
    expect(link).toHaveAttribute('href', '/login');
    // jsdom has no CSS, so guard the class: hiding it on phones left returning users
    // with no visible way in (and its own inline-flex would have overridden `hidden`).
    expect(link.className).not.toMatch(/(^|\s)(max-\w+:)?hidden(\s|$)/);
  });

  it('offers a skip link to the main content', () => {
    renderLanding();
    expect(screen.getByRole('link', { name: 'Skip to content' })).toHaveAttribute('href', '#main');
    expect(screen.getByRole('main')).toHaveAttribute('id', 'main');
  });

  it('keeps the hero flat without WebGL, with nothing over the headline', () => {
    renderLanding();
    // The hero is just the headline, copy, calls to action and the step tabs: no badge,
    // and no overlay control (the tabs are the only buttons in it).
    const hero = screen.getByRole('heading', { level: 1 }).closest('section');
    expect(hero?.querySelectorAll('button:not([role="tab"])')).toHaveLength(0);
    expect(within(hero as HTMLElement).queryByText(/built on/i)).toBeNull();
    // The flat constellation is drawn, and nothing in its container is a WebGL canvas.
    const flat = document.querySelector('svg circle')?.closest('[aria-hidden="true"]');
    expect(flat).not.toBeNull();
    expect(flat?.querySelector('canvas')).toBeNull();
  });

  // This version of AIMIx is closed source: the public page must not advertise a licence,
  // a repository or how to install it, and must not send visitors off-site.
  it('makes no open-source or self-install claims and links nowhere off-site', () => {
    renderLanding();
    expect(document.body.textContent).not.toMatch(
      /open[- ]?source|apache|licen[sc]e|github|self-host|docker|make (install|migrate|run)/i,
    );
    expect(document.querySelectorAll('a[href^="http"]')).toHaveLength(0);
  });
});

describe('hero steps', () => {
  it('shows the first step and swaps the preview when another tab is chosen', async () => {
    renderLanding();
    expect(screen.getByRole('tab', { name: /describe/i })).toHaveAttribute('aria-selected', 'true');

    await userEvent.click(screen.getByRole('tab', { name: /act/i }));

    expect(screen.getByRole('tab', { name: /act/i })).toHaveAttribute('aria-selected', 'true');
    const panel = screen.getByRole('tabpanel');
    expect(await within(panel).findByText(/web_search/)).toBeInTheDocument();
  });

  it('moves between tabs with the arrow keys, keeping one tab in the tab order', async () => {
    renderLanding();
    const first = screen.getByRole('tab', { name: /describe/i });
    first.focus();
    await userEvent.keyboard('{ArrowRight}');

    const second = screen.getByRole('tab', { name: /orchestrate/i });
    expect(second).toHaveAttribute('aria-selected', 'true');
    expect(second).toHaveFocus();
    expect(first).toHaveAttribute('tabindex', '-1');

    await userEvent.keyboard('{End}');
    expect(screen.getByRole('tab', { name: /review/i })).toHaveFocus();
  });
});

describe('FAQ', () => {
  it('opens one answer at a time', async () => {
    renderLanding();
    const models = screen.getByRole('button', { name: 'Which models can I use?' });
    const keys = screen.getByRole('button', { name: 'Do I need my own API key?' });
    expect(models).toHaveAttribute('aria-expanded', 'true');
    expect(keys).toHaveAttribute('aria-expanded', 'false');

    await userEvent.click(keys);

    expect(keys).toHaveAttribute('aria-expanded', 'true');
    expect(models).toHaveAttribute('aria-expanded', 'false');
  });

  it('keeps a closed answer out of the accessibility tree', async () => {
    renderLanding();
    const keys = screen.getByRole('button', { name: 'Do I need my own API key?' });
    const panel = document.getElementById(keys.getAttribute('aria-controls') ?? '');
    expect(panel).toHaveAttribute('inert');

    await userEvent.click(keys);
    expect(panel).not.toHaveAttribute('inert');
  });
});
