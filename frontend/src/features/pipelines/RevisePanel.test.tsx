import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { RevisePanel, type RevisePanelProps } from './RevisePanel';
import { REVISION_EXAMPLES } from './revision';
import { draft, json, pendingFetch, revision } from './revisionTestData';

function renderPanel(props: Partial<RevisePanelProps> = {}) {
  const onApply = vi.fn();
  const panel = (more: Partial<RevisePanelProps>) => (
    <RevisePanel pipeline={draft} onApply={onApply} defaultOpen {...props} {...more} />
  );
  const view = render(panel({}));
  return { onApply, rerender: (more: Partial<RevisePanelProps>) => view.rerender(panel(more)) };
}

const box = () => screen.getByLabelText('What should change?');
const propose = () => screen.getByRole('button', { name: 'Propose changes' });

async function ask(instruction = 'Add an SEO agent alongside the marketing agent') {
  await userEvent.type(box(), instruction);
  await userEvent.click(propose());
}

describe('RevisePanel', () => {
  afterEach(() => vi.restoreAllMocks());

  it('starts folded until it is opened', async () => {
    renderPanel({ defaultOpen: false });
    const toggle = screen.getByRole('button', { name: 'Ask AIMIx to change this pipeline' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');

    await userEvent.click(toggle);

    expect(toggle).toHaveAttribute('aria-expanded', 'true');
  });

  it('fills the box from an example, and asks only once there is text', async () => {
    renderPanel();
    expect(propose()).toBeDisabled();

    await userEvent.click(screen.getByRole('button', { name: REVISION_EXAMPLES[1] }));

    expect(box()).toHaveValue(REVISION_EXAMPLES[1]);
    expect(box()).toHaveFocus();
    expect(propose()).toBeEnabled();
  });

  it('reviews the proposal, then applies it without saving', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(revision));
    const { onApply } = renderPanel();

    await ask();

    expect(await screen.findByText('Adds the step “SEO keywords”')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Proposed changes (1)' })).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Proposal ready: 1 change to review.');
    expect(screen.getByRole('button', { name: /SEO keywords, model, output/ })).toBeDisabled();

    await userEvent.click(screen.getByRole('button', { name: 'Apply changes' }));

    expect(onApply).toHaveBeenCalledTimes(1);
    expect(onApply.mock.calls[0][0]).toMatchObject({ id: 7, name: 'Launch kit' });
    expect(onApply.mock.calls[0][0].steps).toHaveLength(3);
    expect(screen.getByRole('status')).toHaveTextContent('Changes applied. Save the pipeline');
    expect(screen.queryByRole('button', { name: 'Apply changes' })).toBeNull();
    expect(box()).toHaveValue('');
    // Only the revise request: applying never saves.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('discards a proposal and keeps the instruction for another try', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(revision));
    const { onApply } = renderPanel();
    await ask('Add an SEO agent');

    await userEvent.click(await screen.findByRole('button', { name: 'Discard' }));

    expect(onApply).not.toHaveBeenCalled();
    expect(screen.queryByText('Adds the step “SEO keywords”')).toBeNull();
    expect(box()).toHaveValue('Add an SEO agent');
  });

  it('says when there is nothing to change, with nothing to apply', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      json({ ...revision, revised_pipeline: draft, changes: [] }),
    );
    renderPanel();

    await ask();

    expect(await screen.findByRole('heading', { name: 'Nothing to change' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Apply changes' })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(screen.queryByRole('heading', { name: 'Nothing to change' })).toBeNull();
  });

  it('shows why a request failed', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      json({ error: 'upstream_response_invalid', detail: 'Invalid JSON' }, 502),
    );
    renderPanel();

    await ask();

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'AIMIx could not turn that into a change.',
    );
    expect(screen.queryByRole('button', { name: 'Apply changes' })).toBeNull();
  });

  it('shows progress and lets the wait be stopped', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(pendingFetch);
    renderPanel();

    await ask();

    expect(screen.getByRole('status')).toHaveTextContent('AIMIx is working on your change…');
    expect(screen.getByRole('button', { name: 'Working on it…' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Stop' }));
    await waitFor(() => expect(screen.getByRole('status')).toBeEmptyDOMElement());
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('asks with Ctrl+Enter', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(revision));
    renderPanel();

    await userEvent.type(box(), 'Add an SEO agent{Control>}{Enter}{/Control}');

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  });

  it('neither asks nor applies while the page is busy', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(revision));
    const { rerender } = renderPanel();
    await ask();
    await screen.findByText('Adds the step “SEO keywords”');

    rerender({ disabled: true });

    expect(screen.getByRole('button', { name: 'Apply changes' })).toBeDisabled();
    expect(propose()).toBeDisabled();
  });
});
