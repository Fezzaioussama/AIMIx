import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { json } from '../runs/testData';
import { PipelineNav } from './PipelineNav';

function renderNav() {
  return render(
    <MemoryRouter initialEntries={['/pipeline']}>
      <PipelineNav />
    </MemoryRouter>,
  );
}

describe('PipelineNav', () => {
  afterEach(() => vi.restoreAllMocks());

  it('links the four screens and shows no count when nothing waits', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(json({ items: [], total: 0 }));
    renderNav();

    expect(screen.getAllByRole('link').map((link) => link.textContent)).toEqual([
      'Pipeline',
      'Auto Pipeline',
      'Templates',
      'Runs',
    ]);
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(screen.getByRole('link', { name: 'Runs' })).toBeInTheDocument();
  });

  it('shows how many runs wait for you on the Runs tab, in numbers and in words', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ items: [], total: 2 }));
    renderNav();

    const runs = await screen.findByRole('link', { name: 'Runs, 2 waiting for you' });

    expect(runs).toHaveTextContent('Runs2, 2 waiting for you');
    expect(screen.getByRole('link', { name: 'Pipeline' })).toBeInTheDocument();
  });

  it('is still a working menu when the count cannot be fetched', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(json({ error: 'server_error', detail: 'Down.' }, 500));
    renderNav();

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());

    expect(screen.getByRole('link', { name: 'Runs' })).toHaveAttribute('href', '/runs');
  });
});
