import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { json, runStep } from '../runs/testData';
import { MissionPage } from './MissionPage';
import { LocationProbe, renderMission } from './testRender';
import {
  COMMON_ROUTES,
  FILES,
  SAVED,
  finishedRun,
  revisionOf,
  routeFetch,
  runningRun,
  storeAs,
} from './testData';

const log = () => screen.getByRole('log', { name: 'Conversation with AIMIx' });
const teamPane = () => within(screen.getByRole('tabpanel', { name: 'Team' }));

function savedMission(extra: Record<string, unknown> = {}) {
  return routeFetch({ ...COMMON_ROUTES, 'GET /api/pipelines/7/': SAVED, ...extra });
}

/** Pretends the window is as wide as the three panes need (Tailwind's `xl`). */
function stubWideScreen() {
  window.matchMedia = ((query: string) => ({
    matches: true,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  })) as unknown as typeof window.matchMedia;
}

describe('the mission workspace: panes on a narrow screen', () => {
  beforeEach(() => window.sessionStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it('shows one pane at a time as tabs, the conversation first', async () => {
    savedMission();
    renderMission('/mission/7');
    await within(log()).findByText(/Here’s your “Competitor brief” team/);

    expect(screen.getByRole('tab', { name: 'Conversation' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    const panels = ['chat', 'team', 'results'].map((pane) =>
      document.getElementById(`mission-${pane}-panel`),
    );
    expect(panels.map((panel) => panel?.classList.contains('hidden'))).toEqual([false, true, true]);

    await userEvent.click(screen.getByRole('tab', { name: 'Team' }));

    expect(panels.map((panel) => panel?.classList.contains('hidden'))).toEqual([true, false, true]);
    expect(screen.getByRole('tab', { name: 'Team' })).toHaveAttribute('aria-selected', 'true');
    // The panes stay in the page: a message typed before the switch is still there after it.
    expect(screen.getByRole('tabpanel', { name: 'Team' })).toContainElement(
      screen.getByRole('heading', { name: 'Competitor brief', level: 3 }),
    );
  });

  it('keeps a half-written message when the person looks at another pane and comes back', async () => {
    const user = userEvent.setup();
    savedMission();
    renderMission('/mission/7');
    await within(log()).findByText(/Here’s your “Competitor brief” team/);
    await user.type(
      screen.getByRole('textbox', { name: 'Message AIMIx about your team' }),
      'Make it',
    );

    await user.click(screen.getByRole('tab', { name: 'Results' }));
    await user.click(screen.getByRole('tab', { name: 'Conversation' }));

    expect(screen.getByRole('textbox', { name: 'Message AIMIx about your team' })).toHaveValue(
      'Make it',
    );
  });

  it('brings a pane forward and moves focus into it from a link in the conversation', async () => {
    savedMission();
    renderMission('/mission/7');
    await within(log()).findByText(/Here’s your “Competitor brief” team/);

    await userEvent.click(within(log()).getByRole('button', { name: 'See the team' }));

    expect(screen.getByRole('tab', { name: 'Team' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('heading', { name: 'Team', level: 2 })).toHaveFocus();
  });

  it('shows the newest run’s status on the Results tab', async () => {
    const running = runningRun({ id: 12 });
    savedMission({
      'GET /api/runs?limit=1&offset=0&pipeline_id=7': { items: [running], total: 1 },
      'GET /api/runs/12': running,
    });
    renderMission('/mission/7');

    expect(await screen.findByRole('tab', { name: 'Results, run running' })).toBeInTheDocument();
  });

  it('leaves out a title bar that has nothing to offer, but keeps the pane named', async () => {
    savedMission();
    renderMission('/mission/7');
    await within(log()).findByText(/Here’s your “Competitor brief” team/);

    // The results pane has no run yet: its bar is for screen readers only on a phone.
    const heading = screen.getByRole('heading', { name: 'Results', level: 2 });
    expect(heading).toHaveClass('max-xl:sr-only');
    expect(heading.parentElement).toHaveClass('max-xl:sr-only');
  });
});

describe('the mission workspace: panes side by side', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    stubWideScreen();
  });
  afterEach(() => {
    Reflect.deleteProperty(window, 'matchMedia');
    vi.restoreAllMocks();
  });

  it('shows all three as labelled regions, without tabs', async () => {
    savedMission();
    renderMission('/mission/7');
    await within(log()).findByText(/Here’s your “Competitor brief” team/);

    expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
    for (const name of ['Conversation', 'Team', 'Results']) {
      expect(screen.getByRole('region', { name })).toBeInTheDocument();
    }
  });
});

describe('the mission workspace: the team pane', () => {
  beforeEach(() => window.sessionStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it('opens an agent in a drawer, edits it, and hands focus back on close', async () => {
    const user = userEvent.setup();
    savedMission();
    renderMission('/mission/7');
    await within(log()).findByText(/Here’s your “Competitor brief” team/);
    const node = teamPane().getByRole('button', { name: /Market research, .*, Not run/ });

    await user.click(node);

    const drawer = screen.getByRole('dialog', { name: 'Researcher' });
    expect(within(drawer).getByRole('heading', { name: 'Researcher' })).toHaveFocus();
    await user.type(within(drawer).getByLabelText('Agent role'), ' lead');
    expect(screen.getByRole('dialog', { name: 'Researcher lead' })).toBeInTheDocument();
    expect(teamPane().getByText('Saving your changes…')).toBeInTheDocument();

    await user.keyboard('{Escape}');

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(node).toHaveFocus();
  });

  it('switches to another agent without closing', async () => {
    const user = userEvent.setup();
    savedMission();
    renderMission('/mission/7');
    await within(log()).findByText(/Here’s your “Competitor brief” team/);

    await user.click(teamPane().getByRole('button', { name: /Market research, / }));
    await user.click(teamPane().getByRole('button', { name: /Comparison, / }));

    expect(screen.getByRole('dialog', { name: 'Analyst' })).toBeInTheDocument();
  });

  it('removes an agent from the drawer and closes it', async () => {
    const user = userEvent.setup();
    savedMission();
    renderMission('/mission/7');
    await within(log()).findByText(/Here’s your “Competitor brief” team/);
    await user.click(teamPane().getByRole('button', { name: /Comparison, / }));

    await user.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Remove step 2' }),
    );

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(teamPane().getByText(/1 agent · 1 stage/)).toBeInTheDocument();
  });

  it('closes the drawer when a change from the conversation is applied', async () => {
    const user = userEvent.setup();
    savedMission({
      'POST /api/pipelines/revise': revisionOf(SAVED),
      'PUT /api/pipelines/7/': storeAs(7),
    });
    renderMission('/mission/7');
    await within(log()).findByText(/Here’s your “Competitor brief” team/);
    await user.click(teamPane().getByRole('button', { name: /Comparison, / }));
    await user.type(
      screen.getByRole('textbox', { name: 'Message AIMIx about your team' }),
      'Add a fact checker{Enter}',
    );
    await within(log()).findByText('Here’s what I would change (1 change):');

    await user.click(within(log()).getByRole('button', { name: 'Apply' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('saves a saved mission’s edits a moment after the last one', async () => {
    const user = userEvent.setup();
    const server = savedMission({ 'PUT /api/pipelines/7/': storeAs(7) });
    renderMission('/mission/7');
    await within(log()).findByText(/Here’s your “Competitor brief” team/);
    await user.click(teamPane().getByRole('button', { name: /Market research, / }));

    await user.type(screen.getByLabelText('Agent role'), '!');

    await waitFor(() => expect(server.to('PUT', '/api/pipelines/7/')).toHaveLength(1), {
      timeout: 4000,
    });
    expect(
      (server.to('PUT', '/api/pipelines/7/')[0].body as { steps: { role: string }[] }).steps[0]
        .role,
    ).toBe('Researcher!');
    await waitFor(() => expect(teamPane().getByText('Saved')).toBeInTheDocument());
  }, 10000);

  it('says why a mission could not be opened, and leads back to a fresh start', async () => {
    routeFetch({
      ...COMMON_ROUTES,
      'GET /api/pipelines/99/': () =>
        json({ error: 'not_found', detail: 'Pipeline 99 was not found.' }, 404),
    });
    renderMission('/mission/99');

    expect(await screen.findByText(/This mission was not found/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Start a new mission' })).toHaveAttribute(
      'href',
      '/mission',
    );
    // Nothing can be sent to a mission that is not there.
    expect(screen.getByRole('textbox', { name: 'Describe your mission' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
  });

  it('opens the mission in the builder, saving what it has first', async () => {
    const server = savedMission({ 'PUT /api/pipelines/7/': storeAs(7) });
    renderMission('/mission/7');
    await within(log()).findByText(/Here’s your “Competitor brief” team/);

    await userEvent.click(screen.getByRole('button', { name: 'Open in builder' }));

    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/pipeline'));
    expect(JSON.parse(screen.getByTestId('location').dataset.state ?? 'null')).toEqual({
      pipelineId: 7,
    });
    expect(server.to('PUT', '/api/pipelines/7/')).toHaveLength(0); // nothing had changed
  });
});

describe('the mission workspace: the results pane', () => {
  beforeEach(() => window.sessionStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it('leads with a finished run’s deliverables, its details folded behind them', async () => {
    const run = finishedRun();
    savedMission({
      'GET /api/runs?limit=1&offset=0&pipeline_id=7': { items: [run], total: 1 },
      'GET /api/runs/9': run,
    });
    renderMission('/mission/7');

    const deliverables = await screen.findByRole('region', { name: 'Deliverables' });

    expect(await within(deliverables).findByText('Comparison table')).toBeInTheDocument();
    expect(within(deliverables).getByRole('button', { name: 'Copy' })).toBeInTheDocument();
    expect(screen.getByText('Run details').closest('details')).not.toHaveAttribute('open');
    const header = screen.getByRole('heading', { name: 'Results', level: 2 })
      .parentElement as HTMLElement;
    expect(within(header).getByText('Done')).toBeInTheDocument();
    // The team on the centre pane shows what the run did.
    expect(
      teamPane().getByRole('button', { name: /Comparison, .*, output, Done/ }),
    ).toBeInTheDocument();
  });

  it('keeps Stop and its status at the top while the run works, and Resume once it stopped', async () => {
    const user = userEvent.setup();
    const running = runningRun({ id: 12 });
    const stopped = runningRun({
      id: 12,
      status: 'cancelled',
      finished_at: '2026-10-24T10:00:05Z',
    });
    const server = savedMission({
      'GET /api/runs?limit=1&offset=0&pipeline_id=7': { items: [running], total: 1 },
      'GET /api/runs/12': running,
      'POST /api/runs/12/cancel': stopped,
      'POST /api/runs/12/resume': running,
    });
    renderMission('/mission/7');

    await user.click(await screen.findByRole('button', { name: 'Stop the run' }));

    expect(await screen.findByRole('button', { name: 'Resume the run' })).toBeEnabled();
    expect(server.to('POST', '/api/runs/12/cancel')).toHaveLength(1);
    const header = screen.getByRole('heading', { name: 'Results', level: 2 })
      .parentElement as HTMLElement;
    expect(within(header).getByText('Stopped')).toBeInTheDocument();
    // Stopped short: the details stay open, with the reason.
    expect(screen.getByText('Run details').closest('details')).toHaveAttribute('open');

    await user.click(screen.getByRole('button', { name: 'Resume the run' }));

    expect(await screen.findByRole('button', { name: 'Stop the run' })).toBeInTheDocument();
    expect(server.to('POST', '/api/runs/12/resume')).toHaveLength(1);
  });

  it('does not wait for a deliverable that was skipped, and says nothing was made', async () => {
    const skipped = finishedRun({
      steps: [
        {
          ...runStep(1, 'succeeded', 'Research notes'),
          title: 'Market research',
          is_output: false,
        },
        { ...runStep(2, 'skipped'), title: 'Comparison' },
      ],
    });
    savedMission({
      'GET /api/runs?limit=1&offset=0&pipeline_id=7': { items: [skipped], total: 1 },
      'GET /api/runs/9': skipped,
    });
    renderMission('/mission/7');

    const deliverables = await screen.findByRole('region', { name: 'Deliverables' });

    expect(
      await within(deliverables).findByText(
        'No deliverable was made: the steps that make them did not run.',
      ),
    ).toBeInTheDocument();
    expect(within(deliverables).queryByText(/Not finished/)).not.toBeInTheDocument();
  });

  it('names the deliverables to expect before there is a run', async () => {
    savedMission();
    renderMission('/mission/7');

    expect(await screen.findByText('When your team has run, you get this:')).toBeInTheDocument();
    const deliverables = screen.getByRole('region', { name: 'Deliverables' });
    expect(within(deliverables).getByText('Analyst')).toBeInTheDocument();
    expect(within(deliverables).getByText('Comparison result')).toBeInTheDocument();
    expect(screen.queryByText('Run details')).not.toBeInTheDocument();
  });

  it('lists the newest files and links to all of them', async () => {
    savedMission();
    renderMission('/mission/7');

    expect(await screen.findByText('brief.pdf')).toBeInTheDocument();
    expect(screen.getByText('notes.txt')).toBeInTheDocument();
    expect(screen.getByText(/reports · 52 KB/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /All files/ })).toHaveAttribute('href', '/files');
  });

  it('says so when there are no files, and when they could not be loaded', async () => {
    routeFetch({
      ...COMMON_ROUTES,
      'GET /api/pipelines/7/': SAVED,
      'GET /api/files': { ...FILES, files: [] },
    });
    renderMission('/mission/7');
    expect(await screen.findByText('Files your agents save appear here.')).toBeInTheDocument();
    cleanup();

    routeFetch({
      ...COMMON_ROUTES,
      'GET /api/pipelines/7/': SAVED,
      'GET /api/files': () => json({ error: 'server_error', detail: 'Storage is offline.' }, 500),
    });
    renderMission('/mission/7');
    expect(await screen.findByText('Storage is offline.')).toBeInTheDocument();
  });
});

describe('the mission workspace: addresses', () => {
  beforeEach(() => window.sessionStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it('starts a new mission for an address that is not a mission id', async () => {
    routeFetch(COMMON_ROUTES);
    renderMission('/mission/abc');

    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent(/^\/mission$/));
    expect(
      screen.getByRole('heading', { name: 'What do you want to get done?' }),
    ).toBeInTheDocument();
  });

  it('opens another mission afresh when the address changes to it', async () => {
    const other = { ...SAVED, id: 8, name: 'Launch plan' };
    routeFetch({
      ...COMMON_ROUTES,
      'GET /api/pipelines/7/': SAVED,
      'GET /api/pipelines/8/': other,
    });
    function Jump() {
      const navigate = useNavigate();
      return (
        <button type="button" onClick={() => navigate('/mission/8')}>
          Go to 8
        </button>
      );
    }
    render(
      <MemoryRouter initialEntries={['/mission/7']}>
        <Routes>
          <Route path="/mission/:pipelineId?" element={<MissionPage />} />
        </Routes>
        <Jump />
        <LocationProbe />
      </MemoryRouter>,
    );
    await within(log()).findByText(/Here’s your “Competitor brief” team/);

    await userEvent.click(screen.getByRole('button', { name: 'Go to 8' }));

    expect(await within(log()).findByText(/Here’s your “Launch plan” team/)).toBeInTheDocument();
    expect(within(log()).queryByText(/Competitor brief/)).not.toBeInTheDocument();
  });

  it('"New mission" on a saved mission starts a fresh one at /mission', async () => {
    savedMission();
    renderMission('/mission/7');
    await within(log()).findByText(/Here’s your “Competitor brief” team/);

    await userEvent.click(screen.getByRole('button', { name: 'New mission' }));

    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent(/^\/mission$/));
    expect(
      await screen.findByRole('heading', { name: 'What do you want to get done?' }),
    ).toBeInTheDocument();
  });

  it('remembers a saved mission’s conversation for the tab, and says when a reply was missed', async () => {
    const user = userEvent.setup();
    savedMission({ 'POST /api/pipelines/revise': revisionOf(SAVED) });
    const first = renderMission('/mission/7');
    await within(log()).findByText(/Here’s your “Competitor brief” team/);
    await user.type(
      screen.getByRole('textbox', { name: 'Message AIMIx about your team' }),
      'Add a fact checker{Enter}',
    );
    await within(log()).findByText('Here’s what I would change (1 change):');
    first.unmount();
    cleanup();

    savedMission({});
    renderMission('/mission/7');

    expect(within(log()).getByText('Add a fact checker')).toBeInTheDocument();
    expect(within(log()).getByText(/Here’s your “Competitor brief” team/)).toBeInTheDocument();
    // The proposal was waiting for an answer when the page was left; it cannot be applied now.
    expect(within(log()).getByText(/That proposal is no longer available/)).toBeInTheDocument();
    expect(within(log()).queryByRole('button', { name: 'Apply' })).not.toBeInTheDocument();
  });
});
