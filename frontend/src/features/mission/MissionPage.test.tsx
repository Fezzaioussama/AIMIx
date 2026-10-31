import { cleanup, screen, waitFor, within } from '@testing-library/react';
import userEvent, { type UserEvent } from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { json } from '../runs/testData';
import { MISSION_EXAMPLES } from './MissionStart';
import { renderMission } from './testRender';
import {
  COMMON_ROUTES,
  GENERATED,
  SAVED,
  deferred,
  finishedRun,
  revisionOf,
  routeFetch,
  runningRun,
  storeAs,
} from './testData';

const composer = () =>
  screen.getByRole('textbox', { name: /Describe your mission|Message AIMIx about your team/ });
const log = () => screen.getByRole('log', { name: 'Conversation with AIMIx' });

async function say(user: UserEvent, text: string) {
  await user.type(composer(), `${text}{Enter}`);
}

/** A saved mission with no runs yet, as the server has it. */
function savedMission(extra: Record<string, unknown> = {}) {
  return routeFetch({ ...COMMON_ROUTES, 'GET /api/pipelines/7/': SAVED, ...extra });
}

describe('the mission workspace: starting', () => {
  beforeEach(() => window.sessionStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it('opens on what to do, with examples, template quick-starts and recent missions', async () => {
    routeFetch({
      ...COMMON_ROUTES,
      'GET /api/pipelines/': [SAVED, { ...SAVED, id: 8, name: 'Launch plan' }],
    });
    renderMission();

    expect(
      screen.getByRole('heading', { name: 'What do you want to get done?' }),
    ).toBeInTheDocument();
    for (const example of MISSION_EXAMPLES) {
      expect(screen.getByRole('button', { name: example })).toBeInTheDocument();
    }
    expect(await screen.findByRole('button', { name: 'Document digest' })).toBeEnabled();
    expect(await screen.findByRole('link', { name: /Competitor brief/ })).toHaveAttribute(
      'href',
      '/mission/7',
    );
    expect(screen.getByRole('link', { name: /Launch plan/ })).toHaveAttribute('href', '/mission/8');
    // AIMIx's answers are announced as they arrive.
    expect(log()).toHaveAttribute('aria-live', 'polite');
    // Nothing to send yet.
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
  });

  it('fills the message box from an example, ready to send', async () => {
    routeFetch(COMMON_ROUTES);
    renderMission();

    await userEvent.click(screen.getByRole('button', { name: MISSION_EXAMPLES[1] }));

    expect(composer()).toHaveValue(MISSION_EXAMPLES[1]);
    expect(composer()).toHaveFocus();
    expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled();
  });

  it('starts from a template as the person’s own saved mission, and opens its address', async () => {
    const server = routeFetch({
      ...COMMON_ROUTES,
      'POST /api/templates/document-digest/use': { ...SAVED, name: 'Document digest' },
    });
    renderMission();

    await userEvent.click(await screen.findByRole('button', { name: 'Document digest' }));

    expect(await within(log()).findByText(/Here’s the “Document digest” team/)).toBeInTheDocument();
    expect(server.to('POST', '/api/templates/document-digest/use')).toHaveLength(1);
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/mission/7'));
    expect(screen.getByRole('heading', { name: 'Document digest', level: 3 })).toBeInTheDocument();
  });

  it('says so when a template could not be used', async () => {
    routeFetch({
      ...COMMON_ROUTES,
      'POST /api/templates/document-digest/use': () =>
        json({ error: 'server_error', detail: 'Try later.' }, 500),
    });
    renderMission();

    await userEvent.click(await screen.findByRole('button', { name: 'Document digest' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not start "Document digest". Try later.',
    );
  });
});

describe('the mission workspace: describing a mission', () => {
  beforeEach(() => window.sessionStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it('shows the team in words, on the team pane and as what to expect, while nothing is saved', async () => {
    const user = userEvent.setup();
    const planned = deferred<unknown>();
    const server = routeFetch({
      ...COMMON_ROUTES,
      'POST /api/pipelines/generate': () => planned.promise,
    });
    renderMission();

    await say(user, 'Compare my competitors');

    expect(composer()).toHaveValue('');
    expect(within(log()).getByText('Compare my competitors')).toBeInTheDocument();
    expect(within(log()).getByText('Putting your team together…')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
    expect(screen.getByText('AIMIx is putting your team together…')).toBeInTheDocument();

    planned.resolve(GENERATED);

    expect(
      await within(log()).findByText(/Here’s the team I put together for “Competitor brief”/),
    ).toBeInTheDocument();
    expect(within(log()).getByText('Researcher')).toBeInTheDocument();
    expect(within(log()).getByText('Analyst')).toBeInTheDocument();
    expect(within(log()).getByText('Works without tools')).toBeInTheDocument();
    expect(within(log()).getByText('Can use any of your tools')).toBeInTheDocument();
    expect(within(log()).getByText('You provide: Your company.')).toBeInTheDocument();
    // The team pane and the results pane know it too.
    expect(screen.getByRole('heading', { name: 'Competitor brief', level: 3 })).toBeInTheDocument();
    expect(screen.getByText('Saved when you first run it')).toBeInTheDocument();
    expect(screen.getByRole('list', { name: 'Pipeline diagram' })).toBeInTheDocument();
    expect(screen.getByText('When your team has run, you get this:')).toBeInTheDocument();
    expect(composer()).toHaveAccessibleName('Message AIMIx about your team');
    expect(screen.getByRole('button', { name: 'Run it' })).toBeInTheDocument();
    expect(server.to('POST', '/api/pipelines/')).toHaveLength(0);
  });

  it('can be stopped while it works', async () => {
    const user = userEvent.setup();
    routeFetch({
      ...COMMON_ROUTES,
      'POST /api/pipelines/generate': (init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () =>
            reject(new DOMException('aborted', 'AbortError')),
          );
        }),
    });
    renderMission();
    await say(user, 'Compare my competitors');

    await user.click(within(log()).getByRole('button', { name: 'Stop' }));

    expect(
      await within(log()).findByText(/^Stopped\. Describe your mission again/),
    ).toBeInTheDocument();
    expect(screen.queryByText('Putting your team together…')).not.toBeInTheDocument();
    expect(composer()).toHaveAccessibleName('Describe your mission');
  });

  it('gives a plain answer when no team could be made', async () => {
    const user = userEvent.setup();
    routeFetch({
      ...COMMON_ROUTES,
      'POST /api/pipelines/generate': () =>
        json({ error: 'provider_not_configured', detail: 'No API key is set.' }, 503),
    });
    renderMission();

    await say(user, 'Compare my competitors');

    expect(await within(log()).findByText('No API key is set.')).toBeInTheDocument();
  });

  it('keeps the conversation and the draft team for this tab, and starts over on request', async () => {
    const user = userEvent.setup();
    routeFetch({ ...COMMON_ROUTES, 'POST /api/pipelines/generate': GENERATED });
    const first = renderMission();
    await say(user, 'Compare my competitors');
    await within(log()).findByText(/Here’s the team I put together/);
    first.unmount();
    cleanup();

    renderMission();

    expect(within(log()).getByText('Compare my competitors')).toBeInTheDocument();
    expect(within(log()).getByText(/Here’s the team I put together/)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Competitor brief', level: 3 })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'New mission' }));

    expect(
      screen.getByRole('heading', { name: 'What do you want to get done?' }),
    ).toBeInTheDocument();
    expect(screen.queryByText('Compare my competitors')).not.toBeInTheDocument();
    cleanup();
    renderMission();
    expect(
      screen.getByRole('heading', { name: 'What do you want to get done?' }),
    ).toBeInTheDocument();
  });
});

describe('the mission workspace: asking for changes', () => {
  beforeEach(() => window.sessionStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  async function openSaved() {
    const server = savedMission({
      'POST /api/pipelines/revise': revisionOf(SAVED),
      'PUT /api/pipelines/7/': storeAs(7),
    });
    renderMission('/mission/7');
    await within(log()).findByText(/Here’s your “Competitor brief” team/);
    return server;
  }

  it('answers with the changes in words, and Apply changes the team and saves it', async () => {
    const user = userEvent.setup();
    const server = await openSaved();

    await say(user, 'Add an agent that checks the facts');
    expect(
      await within(log()).findByText('Here’s what I would change (1 change):'),
    ).toBeInTheDocument();
    expect(within(log()).getByText('Adds the step “Fact check”')).toBeInTheDocument();
    expect(screen.getByText(/2 agents · 2 stages/)).toBeInTheDocument();

    await user.click(within(log()).getByRole('button', { name: 'Apply' }));

    expect(await within(log()).findByText('Done. I applied 1 change:')).toBeInTheDocument();
    expect(screen.getByText(/3 agents · 3 stages/)).toBeInTheDocument();
    expect(composer()).toHaveFocus();
    await waitFor(() => expect(server.to('PUT', '/api/pipelines/7/')).toHaveLength(1));
    // The change is kept, and the old proposal's buttons are gone.
    expect(within(log()).queryByRole('button', { name: 'Apply' })).not.toBeInTheDocument();
  });

  it('Discard leaves the team as it was', async () => {
    const user = userEvent.setup();
    const server = await openSaved();
    await say(user, 'Add an agent that checks the facts');
    await within(log()).findByText('Here’s what I would change (1 change):');

    await user.click(within(log()).getByRole('button', { name: 'Discard' }));

    expect(within(log()).getByText('Discarded. The team stays as it was.')).toBeInTheDocument();
    expect(screen.getByText(/2 agents · 2 stages/)).toBeInTheDocument();
    expect(composer()).toHaveFocus();
    expect(server.to('PUT', '/api/pipelines/7/')).toHaveLength(0);
  });

  it('previews the new team before anything is applied', async () => {
    const user = userEvent.setup();
    await openSaved();
    await say(user, 'Add an agent that checks the facts');
    await within(log()).findByText('Here’s what I would change (1 change):');

    await user.click(within(log()).getByText('Preview the new team'));

    expect(within(log()).getByRole('list', { name: 'Pipeline diagram' })).toBeInTheDocument();
    expect(
      within(log()).getByRole('button', { name: /Fact check, .*, output, Not run/ }),
    ).toBeInTheDocument();
  });

  it('says plainly when the change could not be worked out', async () => {
    const user = userEvent.setup();
    routeFetch({
      ...COMMON_ROUTES,
      'GET /api/pipelines/7/': SAVED,
      'POST /api/pipelines/revise': () =>
        json({ error: 'upstream_response_invalid', detail: 'bad json' }, 502),
    });
    renderMission('/mission/7');
    await within(log()).findByText(/Here’s your “Competitor brief” team/);

    await say(user, 'Add an agent that checks the facts');

    expect(
      await within(log()).findByText(
        'AIMIx could not turn that into a change. Try saying it another way.',
      ),
    ).toBeInTheDocument();
  });

  it('says so when there was nothing to change', async () => {
    const user = userEvent.setup();
    routeFetch({
      ...COMMON_ROUTES,
      'GET /api/pipelines/7/': SAVED,
      'POST /api/pipelines/revise': { ...revisionOf(SAVED), changes: [] },
    });
    renderMission('/mission/7');
    await within(log()).findByText(/Here’s your “Competitor brief” team/);

    await say(user, 'Leave everything as it is');

    expect(await within(log()).findByText(/Nothing to change/)).toBeInTheDocument();
    await user.click(within(log()).getByRole('button', { name: 'Close' }));
    expect(within(log()).queryByRole('button', { name: 'Close' })).not.toBeInTheDocument();
  });
});

describe('the mission workspace: running', () => {
  beforeEach(() => window.sessionStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it('asks for the inputs in the conversation, runs, and follows the run to its deliverables', async () => {
    const user = userEvent.setup();
    const done = finishedRun();
    const server = savedMission({
      'POST /api/pipelines/7/runs': runningRun({ id: 9 }),
      'GET /api/runs/9': done,
    });
    renderMission('/mission/7');
    await within(log()).findByText(/Here’s your “Competitor brief” team/);

    await user.click(screen.getByRole('button', { name: 'Run it' }));

    expect(
      await within(log()).findByText(/Here’s what your team needs to start/),
    ).toBeInTheDocument();
    const field = within(log()).getByLabelText(/Your company/);
    expect(field).toHaveFocus();
    expect(within(log()).getByText('Attach a document')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Run it' })).not.toBeInTheDocument();
    const run = within(log()).getByRole('button', { name: 'Run Pipeline' });
    expect(run).toBeDisabled();

    await user.type(field, 'Acme');
    await user.click(run);

    expect(await within(log()).findByText('Inputs sent.')).toBeInTheDocument();
    expect(server.to('POST', '/api/pipelines/7/runs')[0].body).toEqual({
      inputs: { company: 'Acme' },
    });
    expect(composer()).toHaveFocus();
    expect(within(log()).getByText(/Your team is on it/)).toBeInTheDocument();
    // The status and its control are always in reach at the top of the results pane.
    expect(screen.getByRole('button', { name: 'Stop the run' })).toBeEnabled();
    expect(screen.getAllByText('Running').length).toBeGreaterThan(0);
    // Editing waits: the agents on the team pane cannot be opened mid-run.
    const team = within(screen.getByRole('tabpanel', { name: 'Team' }));
    expect(team.getByRole('button', { name: /Market research, .*, Done/ })).toBeDisabled();
    expect(team.getByText(/Your team is working/)).toBeInTheDocument();

    // One poll later the run is done: its deliverables lead the results.
    expect(
      await within(log()).findByText(/1 deliverable is ready under Results/, undefined, {
        timeout: 4000,
      }),
    ).toBeInTheDocument();
    const results = screen.getByRole('region', { name: 'Deliverables' });
    expect(within(results).getByText('Comparison table')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Stop the run' })).not.toBeInTheDocument();
    expect(screen.getByText('Run details').closest('details')).not.toHaveAttribute('open');
    // What the agents saved is listed again once the run has ended.
    await waitFor(() => expect(server.to('GET', '/api/files').length).toBeGreaterThanOrEqual(2));
  }, 15000);

  it('runs a free-text mission from one box', async () => {
    const user = userEvent.setup();
    const server = routeFetch({
      ...COMMON_ROUTES,
      'GET /api/pipelines/7/': { ...SAVED, inputs: [] },
      'POST /api/pipelines/7/runs': runningRun({
        id: 9,
        definition: { name: 'x', inputs: [], steps: SAVED.steps },
      }),
    });
    renderMission('/mission/7');
    await within(log()).findByText(/Here’s your “Competitor brief” team/);

    await say(user, 'run it');
    await user.type(await within(log()).findByLabelText('Run input'), 'Our coffee grinder');
    await user.click(within(log()).getByRole('button', { name: 'Run Pipeline' }));

    await within(log()).findByText('Inputs sent.');
    expect(server.to('POST', '/api/pipelines/7/runs')[0].body).toEqual({
      input: 'Our coffee grinder',
    });
  });

  it('saves a new mission when it first runs and moves to its own address without starting over', async () => {
    const user = userEvent.setup();
    const server = routeFetch({
      ...COMMON_ROUTES,
      'POST /api/pipelines/generate': GENERATED,
      'POST /api/pipelines/': storeAs(7),
      'POST /api/pipelines/7/runs': runningRun({ id: 9 }),
      'GET /api/runs/9': runningRun({ id: 9 }),
    });
    renderMission();
    await say(user, 'Compare my competitors');
    await within(log()).findByText(/Here’s the team I put together/);
    expect(screen.getByTestId('location')).toHaveTextContent(/^\/mission$/);

    await say(user, 'Run it please');
    await user.type(await within(log()).findByLabelText(/Your company/), 'Acme');
    await user.click(within(log()).getByRole('button', { name: 'Run Pipeline' }));

    await within(log()).findByText('Inputs sent.');
    expect(server.to('POST', '/api/pipelines/')).toHaveLength(1);
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/mission/7'));
    // Still the same workspace: nothing was lost on the way.
    expect(within(log()).getByText(/Here’s the team I put together/)).toBeInTheDocument();
    expect(within(log()).getByText(/Your team is on it/)).toBeInTheDocument();
    expect(screen.getByText('Saved')).toBeInTheDocument();
  });

  it('keeps the form and says why when the run does not start', async () => {
    const user = userEvent.setup();
    savedMission({
      'POST /api/pipelines/7/runs': () =>
        json({ error: 'validation_error', detail: 'The mission could not start.' }, 400),
    });
    renderMission('/mission/7');
    await within(log()).findByText(/Here’s your “Competitor brief” team/);
    await user.click(screen.getByRole('button', { name: 'Run it' }));
    await user.type(await within(log()).findByLabelText(/Your company/), 'Acme');

    await user.click(within(log()).getByRole('button', { name: 'Run Pipeline' }));

    expect(await within(log()).findByText('The mission could not start.')).toBeInTheDocument();
    expect(within(log()).getByLabelText(/Your company/)).toHaveValue('Acme');
  });

  it('will not run twice at once', async () => {
    const user = userEvent.setup();
    savedMission({
      'GET /api/runs?limit=1&offset=0&pipeline_id=7': { items: [runningRun({ id: 12 })], total: 1 },
      'GET /api/runs/12': runningRun({ id: 12 }),
    });
    renderMission('/mission/7');
    await within(log()).findByText(/Here’s your “Competitor brief” team/);
    await screen.findByRole('button', { name: 'Stop the run' });
    expect(screen.queryByRole('button', { name: 'Run it' })).not.toBeInTheDocument();

    await say(user, 'run it');

    expect(within(log()).getByText(/still working on the last run/)).toBeInTheDocument();
  });

  it('treats "run it" as a description while there is no team yet', async () => {
    const user = userEvent.setup();
    const server = routeFetch({ ...COMMON_ROUTES, 'POST /api/pipelines/generate': GENERATED });
    renderMission();

    await say(user, 'run it');

    await within(log()).findByText(/Here’s the team I put together/);
    expect(server.to('POST', '/api/pipelines/generate')[0].body).toEqual({
      description: 'run it',
      may_ask: true,
      answers: [],
    });
  });
});
