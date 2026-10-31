import { render, screen, within } from '@testing-library/react';
import { FolderOpen, History, Rocket } from 'lucide-react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { SidebarNav, type NavGroup } from './SidebarNav';

function groups(waiting: number): NavGroup[] {
  return [
    { items: [{ to: '/mission', label: 'Missions', icon: Rocket }] },
    {
      label: 'Pipelines',
      items: [
        {
          to: '/runs',
          label: 'Runs',
          icon: History,
          badge: { count: waiting, label: 'waiting for you' },
        },
      ],
    },
    { label: 'Workspace', items: [{ to: '/files', label: 'Files', icon: FolderOpen }] },
  ];
}

function renderAt(path: string, waiting = 0) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <SidebarNav groups={groups(waiting)} pillId="test-nav" />
    </MemoryRouter>,
  );
}

describe('SidebarNav', () => {
  it('names each group after its heading; the first goes without one', () => {
    renderAt('/files');
    const lists = screen.getAllByRole('list');
    expect(lists).toHaveLength(3);
    expect(lists[0]).not.toHaveAccessibleName();
    expect(
      within(screen.getByRole('list', { name: 'Workspace' })).getByRole('link'),
    ).toHaveTextContent('Files');
  });

  it('marks the item that owns the address, and the addresses below it', () => {
    renderAt('/runs/7');
    expect(screen.getByRole('link', { name: 'Runs' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Missions' })).not.toHaveAttribute('aria-current');
  });

  it('does not mark an item whose address only starts the same way', () => {
    renderAt('/runsheet');
    expect(screen.getByRole('link', { name: 'Runs' })).not.toHaveAttribute('aria-current');
  });

  it('shows a count only when there is something to count', () => {
    const { unmount } = renderAt('/files');
    expect(screen.getByRole('link', { name: 'Runs' })).toHaveTextContent(/^Runs$/);
    unmount();

    renderAt('/files', 3);
    expect(screen.getByRole('link', { name: 'Runs, 3 waiting for you' })).toBeInTheDocument();
  });
});
