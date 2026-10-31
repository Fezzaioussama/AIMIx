import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FolderOpen, Rocket } from 'lucide-react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { AppFrame } from './AppFrame';
import type { NavGroup } from './SidebarNav';

const GROUPS: NavGroup[] = [
  { items: [{ to: '/mission', label: 'Missions', icon: Rocket }] },
  { label: 'Workspace', items: [{ to: '/files', label: 'Files', icon: FolderOpen }] },
];

// jsdom answers no media query, so the frame is in its phone layout: the menu opens the nav.
function renderFrame(onLogout = vi.fn()) {
  render(
    <MemoryRouter initialEntries={['/mission']}>
      <AppFrame groups={GROUPS} onLogout={onLogout}>
        <Routes>
          <Route path="/mission" element={<button type="button">On the mission</button>} />
          <Route path="/files" element={<p>The files</p>} />
        </Routes>
      </AppFrame>
    </MemoryRouter>,
  );
  return onLogout;
}

const menuButton = () => screen.getByRole('button', { name: 'Open menu' });

describe('AppFrame', () => {
  it('opens the menu as a dialog, focused on Close, with the screen behind it inert', async () => {
    const user = userEvent.setup();
    renderFrame();
    expect(menuButton()).toHaveAttribute('aria-expanded', 'false');

    await user.click(menuButton());

    const menu = screen.getByRole('dialog', { name: 'Menu' });
    expect(within(menu).getByRole('link', { name: 'Files' })).toBeInTheDocument();
    expect(within(menu).getByRole('button', { name: 'Close menu' })).toHaveFocus();
    expect(menuButton()).toHaveAttribute('aria-expanded', 'true');
    expect(menuButton()).toHaveAttribute('aria-controls', menu.id);
    expect(screen.getByText('On the mission').closest('[inert]')).not.toBeNull();
  });

  it('closes on Escape and hands focus back to the menu button', async () => {
    const user = userEvent.setup();
    renderFrame();
    await user.click(menuButton());

    await user.keyboard('{Escape}');

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(menuButton()).toHaveFocus();
    expect(screen.getByText('On the mission').closest('[inert]')).toBeNull();
  });

  it('closes once one of its links is followed', async () => {
    const user = userEvent.setup();
    renderFrame();
    await user.click(menuButton());

    await user.click(within(screen.getByRole('dialog')).getByRole('link', { name: 'Files' }));

    expect(await screen.findByText('The files')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('logs out from the menu', async () => {
    const user = userEvent.setup();
    const onLogout = renderFrame();
    await user.click(menuButton());

    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Log out' }));

    expect(onLogout).toHaveBeenCalledOnce();
  });
});
