import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Run } from '../../core/api/types';
import { renderMission } from './testRender';
import { COMMON_ROUTES, SAVED, deferred, finishedRun, routeFetch, runningRun } from './testData';

const HISTORY = 'GET /api/runs?limit=1&offset=0&pipeline_id=7';
const THREE_PANES = 'grid-cols-[20rem_minmax(0,1fr)_22rem]';

const log = () => screen.getByRole('log', { name: 'Conversation with AIMIx' });
const panel = (pane: string) => document.getElementById(`mission-${pane}-panel`) as HTMLElement;
const greeted = () => within(log()).findByText(/Here’s your “Competitor brief” team/);

/** Lets what the screen does after showing a change (its effects) happen too. */
async function settle() {
  await act(() => new Promise((done) => setTimeout(done, 0)));
}

function savedMission(extra: Record<string, unknown> = {}) {
  return routeFetch({ ...COMMON_ROUTES, 'GET /api/pipelines/7/': SAVED, ...extra });
}

/** The mission opened with `run` as its newest run. */
function missionWithRun(run: Run) {
  return savedMission({ [HISTORY]: { items: [run], total: 1 }, [`GET /api/runs/${run.id}`]: run });
}

/** Pretends the window is as wide as the panes need side by side (Tailwind's `xl`). */
function stubWideScreen() {
  window.matchMedia = ((query: string) => ({
    matches: true,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  })) as unknown as typeof window.matchMedia;
}

/** Every class list an element of the page has had since this was called. */
function recordClasses() {
  const seen = new Set<string>();
  const note = (element: Element) => seen.add(element.getAttribute('class') ?? '');
  const read = (records: MutationRecord[]) => {
    for (const record of records) {
      if (record.oldValue !== null) seen.add(record.oldValue);
      if (record.target instanceof Element) note(record.target);
      record.addedNodes.forEach((node) => {
        if (node instanceof Element) [node, ...node.querySelectorAll('[class]')].forEach(note);
      });
    }
  };
  document.body.querySelectorAll('[class]').forEach(note);
  const observer = new MutationObserver(read);
  observer.observe(document.body, {
    subtree: true,
    childList: true,
    attributes: true,
    attributeFilter: ['class'],
    attributeOldValue: true,
  });
  return {
    /** Whether any class list so far held `part`; stops recording. */
    hadAny: (part: string) => {
      read(observer.takeRecords());
      observer.disconnect();
      return [...seen].some((classes) => classes.includes(part));
    },
  };
}

describe('the mission layout on a wide screen', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    stubWideScreen();
  });
  afterEach(() => {
    Reflect.deleteProperty(window, 'matchMedia');
    vi.restoreAllMocks();
  });

  it('shows all three as labelled regions, without tabs, before the team has run', async () => {
    savedMission();
    renderMission('/mission/7');
    await greeted();

    await waitFor(() => expect(panel('results')).not.toHaveClass('hidden'));
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
    for (const name of ['Conversation', 'Team', 'Results']) {
      expect(screen.getByRole('region', { name })).toBeInTheDocument();
    }
  });

  it('sets a run’s results beside the conversation, the team one tab away', async () => {
    const user = userEvent.setup();
    missionWithRun(finishedRun());
    renderMission('/mission/7');

    const results = await screen.findByRole('tab', { name: 'Results, run done' });

    expect(screen.getByRole('region', { name: 'Conversation' })).toBeInTheDocument();
    expect(screen.getByRole('tablist', { name: 'Mission' })).toBeInTheDocument();
    expect(screen.getAllByRole('tab').map((tab) => tab.id)).toEqual([
      'mission-team-tab',
      'mission-results-tab',
    ]);
    await waitFor(() => expect(results).toHaveAttribute('aria-selected', 'true'));
    const shown = within(screen.getByRole('tabpanel', { name: 'Results, run done' }));
    expect(
      await shown.findByRole('heading', { name: '1 deliverable ready', level: 3 }),
    ).toBeInTheDocument();
    expect(panel('team')).toHaveClass('hidden');
    // The tab names the pane: its title bar is for screen readers only.
    expect(screen.getByRole('heading', { name: 'Results', level: 2 })).toHaveClass('sr-only');

    await user.click(screen.getByRole('tab', { name: 'Team' }));

    expect(panel('team')).not.toHaveClass('hidden');
    expect(panel('results')).toHaveClass('hidden');
    expect(panel('chat')).not.toHaveClass('hidden');
    expect(
      within(panel('team')).getByRole('button', { name: 'Open in builder' }),
    ).toBeInTheDocument();
  });

  it('waits for the newest run before setting out the panes, so they never jump', async () => {
    const listed = deferred<object>();
    const run = finishedRun();
    savedMission({ [HISTORY]: () => listed.promise, 'GET /api/runs/9': run });
    const classes = recordClasses();
    renderMission('/mission/7');
    await greeted();

    expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
    expect(screen.getByText('Loading your mission…')).toBeInTheDocument();
    expect(panel('team')).toHaveClass('hidden');
    expect(panel('results')).toHaveClass('hidden');
    expect(panel('chat')).not.toHaveClass('hidden');

    listed.resolve({ items: [run], total: 1 });

    expect(await screen.findByRole('tablist', { name: 'Mission' })).toBeInTheDocument();
    expect(screen.queryByText('Loading your mission…')).not.toBeInTheDocument();
    expect(classes.hadAny(THREE_PANES)).toBe(false);
  });

  it('brings a run started in the conversation forward, the typing left where it is', async () => {
    const user = userEvent.setup();
    savedMission({
      'POST /api/pipelines/7/runs': runningRun({ id: 9 }),
      'GET /api/runs/9': runningRun({ id: 9 }),
    });
    renderMission('/mission/7');
    await greeted();
    await waitFor(() => expect(panel('team')).not.toHaveClass('hidden'));
    // The person looked at the team last: the new run's results still come forward.
    await user.click(within(log()).getByRole('button', { name: 'See the team' }));

    await user.click(screen.getByRole('button', { name: 'Run it' }));
    await user.type(await within(log()).findByLabelText(/Your company/), 'Acme');
    await user.click(within(log()).getByRole('button', { name: 'Run Pipeline' }));
    await within(log()).findByText('Inputs sent.');

    expect(await screen.findByRole('tab', { name: 'Results, run running' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(panel('team')).toHaveClass('hidden');
    expect(screen.getByRole('textbox', { name: 'Message AIMIx about your team' })).toHaveFocus();
  });

  it('keeps the team in front once picked while the same run goes on', async () => {
    const user = userEvent.setup();
    const running = runningRun({ id: 12 });
    missionWithRun(running);
    renderMission('/mission/7');
    const results = await screen.findByRole('tab', { name: 'Results, run running' });
    await waitFor(() => expect(results).toHaveAttribute('aria-selected', 'true'));

    await user.click(screen.getByRole('tab', { name: 'Team' }));

    expect(screen.getByRole('tab', { name: 'Team' })).toHaveAttribute('aria-selected', 'true');
    expect(panel('results')).toHaveClass('hidden');
  });
});

describe('the mission layout on a narrow screen', () => {
  beforeEach(() => window.sessionStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it('opens on the results of a run found with the mission, without moving focus', async () => {
    missionWithRun(finishedRun());
    renderMission('/mission/7');

    const results = await screen.findByRole('tab', { name: 'Results, run done' });

    await waitFor(() => expect(results).toHaveAttribute('aria-selected', 'true'));
    expect(screen.getAllByRole('tab')).toHaveLength(3);
    expect(document.body).toHaveFocus();
  });

  it('stays on the pane the person picked before the run loaded', async () => {
    const user = userEvent.setup();
    const listed = deferred<object>();
    const run = finishedRun();
    savedMission({ [HISTORY]: () => listed.promise, 'GET /api/runs/9': run });
    renderMission('/mission/7');
    await greeted();

    await user.click(screen.getByRole('tab', { name: 'Team' }));
    listed.resolve({ items: [run], total: 1 });

    const results = await screen.findByRole('tab', { name: 'Results, run done' });
    await settle();

    expect(results).toHaveAttribute('aria-selected', 'false');
    expect(screen.getByRole('tab', { name: 'Team' })).toHaveAttribute('aria-selected', 'true');
  });

  it('says the results are loading while the newest run is looked up', async () => {
    const listed = deferred<object>();
    savedMission({ [HISTORY]: () => listed.promise });
    renderMission('/mission/7');
    await greeted();

    expect(within(panel('results')).getByText('Loading your results…')).toBeInTheDocument();

    listed.resolve({ items: [], total: 0 });

    expect(
      await within(panel('results')).findByText('When your team has run, you get this:'),
    ).toBeInTheDocument();
    expect(within(panel('results')).queryByText('Loading your results…')).not.toBeInTheDocument();
  });
});
