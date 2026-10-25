import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import { json } from '../settings/testData';
import { TemplatesPage } from './TemplatesPage';
import { TEMPLATES } from './testData';

// The sub-navigation counts waiting runs with a request of its own, and these tests
// answer fetch calls in order, for the gallery alone.
vi.mock('../runs/useWaitingRuns', () => ({ useWaitingRuns: () => 0 }));

/** Stands in for the builder, showing the router state it was opened with. */
function BuilderProbe() {
  const state: unknown = useLocation().state;
  return <p>Builder opened with {JSON.stringify(state)}</p>;
}

function renderGallery() {
  return render(
    <MemoryRouter initialEntries={['/templates']}>
      <Routes>
        <Route path="/templates" element={<TemplatesPage />} />
        <Route path="/pipeline" element={<BuilderProbe />} />
      </Routes>
    </MemoryRouter>,
  );
}

async function findCard(title: string): Promise<HTMLElement> {
  const heading = await screen.findByRole('heading', { level: 2, name: title });
  const card = heading.closest('li');
  if (!card) throw new Error(`No card for ${title}`);
  return card;
}

const created = (id: number) => json({ id, name: 'Document digest', inputs: [], steps: [] }, 201);

describe('TemplatesPage', () => {
  afterEach(() => vi.restoreAllMocks());

  it('shows each template with what it asks for and the size of its team', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(TEMPLATES));
    renderGallery();

    const card = await findCard('Market research brief');

    expect(screen.getByRole('heading', { level: 1, name: 'Start from a template' })).toBeVisible();
    expect(within(card).getByText('Market, Your goal')).toBeInTheDocument();
    expect(within(card).getByText('5 agents')).toBeInTheDocument();
    expect(within(card).getByText('3 stages')).toBeInTheDocument();
    // An input without a label is shown by its name; one agent is not "1 agents".
    const unlabelled = await findCard('Competitor analysis');
    expect(within(unlabelled).getByText('Your product, competitors')).toBeInTheDocument();
    expect(within(await findCard('Document digest')).getByText('1 agent')).toBeInTheDocument();
  });

  it('filters the gallery by category', async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(TEMPLATES));
    renderGallery();

    await user.click(await screen.findByRole('button', { name: 'Documents' }));

    expect(screen.getByRole('button', { name: 'Documents' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByRole('button', { name: 'All' })).toHaveAttribute('aria-pressed', 'false');
    const titles = screen.getAllByRole('heading', { level: 2 }).map((title) => title.textContent);
    expect(titles).toEqual(['Document digest']);
  });

  it('turns a template into a pipeline and opens it in the builder', async () => {
    const user = userEvent.setup();
    let finish: (response: Response) => void = () => undefined;
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json(TEMPLATES))
      .mockImplementationOnce(() => new Promise<Response>((resolve) => (finish = resolve)));
    const scrollTo = vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);
    renderGallery();

    await user.click(await screen.findByRole('button', { name: /^Use this template: Document/ }));

    // While it is created, the card says so and no other template can start.
    expect(screen.getByRole('button', { name: 'Creating…: Document digest' })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Market research brief$/ })).toBeDisabled();
    expect(screen.getByText('Creating your pipeline from Document digest…')).toBeInTheDocument();
    finish(created(42));

    expect(await screen.findByText('Builder opened with {"pipelineId":42}')).toBeInTheDocument();
    expect(fetchMock.mock.calls[1][0]).toBe(API.createFromTemplate('document-digest'));
    // The builder opens at its top, wherever the card was in the gallery.
    expect(scrollTo).toHaveBeenCalledWith({ top: 0 });
  });

  it('explains a failure and lets the user try again', async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json(TEMPLATES))
      .mockResolvedValueOnce(json({ error: 'server_error', detail: 'Something broke.' }, 500));
    renderGallery();

    await user.click(await screen.findByRole('button', { name: /^Use this template: Document/ }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not start "Document digest". Something broke.',
    );
    expect(screen.getByRole('button', { name: /^Use this template: Document/ })).toBeEnabled();
  });

  it('offers to load the gallery again when it cannot be loaded', async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json({ error: 'server_error', detail: 'Something broke.' }, 500))
      .mockResolvedValueOnce(json(TEMPLATES));
    renderGallery();

    expect(await screen.findByRole('alert')).toHaveTextContent('Something broke.');
    await user.click(screen.getByRole('button', { name: 'Try again' }));

    expect(await findCard('Document digest')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
