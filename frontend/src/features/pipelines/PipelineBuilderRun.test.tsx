import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MotionGlobalConfig } from 'motion/react';
import { MemoryRouter } from 'react-router-dom';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import type { Run } from '../../core/api/types';
import {
  COMMON_ROUTES,
  SAVED,
  deferred,
  finishedRun,
  routeFetch,
  runningRun,
} from '../mission/testData';
import { makeApproval } from '../runs/testData';
import { PipelineBuilderPage } from './PipelineBuilderPage';

type Routes = Parameters<typeof routeFetch>[0];

/** The builder opened on `SAVED`, whose newest run is `latest` (none by default). */
function openBuilder(latest: Run | null = null, routes: Routes = {}) {
  const server = routeFetch({
    ...COMMON_ROUTES,
    'GET /api/pipelines/': [SAVED],
    'GET /api/runs': { items: latest ? [latest] : [], total: latest ? 1 : 0 },
    ...(latest ? { [`GET /api/runs/${latest.id}`]: latest } : {}),
    ...routes,
  });
  render(
    <MemoryRouter initialEntries={[{ pathname: '/pipeline', state: { pipelineId: SAVED.id } }]}>
      <PipelineBuilderPage />
    </MemoryRouter>,
  );
  return server;
}

const latestRun = () => screen.findByRole('region', { name: 'Latest run' });
const diagram = () => screen.getByRole('list', { name: 'Pipeline diagram' });

describe('PipelineBuilderPage: the latest run', () => {
  // The report's text swaps wait for their exit; the specs read the end state.
  beforeAll(() => {
    MotionGlobalConfig.skipAnimations = true;
  });
  afterAll(() => {
    MotionGlobalConfig.skipAnimations = false;
  });
  afterEach(() => vi.restoreAllMocks());

  it('hands the run over as its report under the run form, with no output tabs', async () => {
    openBuilder(finishedRun());

    const report = within(await latestRun());
    const outcome = await report.findByRole('heading', { level: 2, name: '1 deliverable ready' });
    expect(report.getByRole('link', { name: 'Open in Runs' })).toHaveAttribute('href', '/runs/9');
    expect(report.getByRole('region', { name: 'Deliverables' })).toHaveTextContent(
      'Comparison table',
    );
    // The page's h1, then the run form's h2, then the report one level below the h1.
    const form = screen.getByRole('heading', { level: 2, name: 'Run Execution' });
    expect(form.compareDocumentPosition(outcome)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(screen.queryByRole('tab', { name: /Outputs|All steps/ })).not.toBeInTheDocument();
    expect(
      screen.queryByText('This run used an earlier version of this pipeline.'),
    ).not.toBeInTheDocument();
  });

  it('shows the run on the diagram it ran, a finished agent opening its step', async () => {
    openBuilder(finishedRun());
    await latestRun();

    expect(within(diagram()).getByRole('button', { name: /^Comparison, .*Done/ })).toBeEnabled();
    expect(within(diagram()).queryByText(/· view/)).not.toBeInTheDocument();
  });

  it('notes a run of an earlier version, and leaves the diagram to the pipeline on screen', async () => {
    const earlier = finishedRun({
      definition: { name: SAVED.name, inputs: [], steps: SAVED.steps },
    });
    openBuilder(earlier);

    const report = within(await latestRun());
    expect(
      await report.findByText('This run used an earlier version of this pipeline.'),
    ).toBeInTheDocument();
    expect(within(diagram()).queryByRole('button', { name: /Done/ })).not.toBeInTheDocument();
  });

  it('keeps the diagram’s agents inert while the run works, and stops it from the report', async () => {
    const server = openBuilder(runningRun(), { 'POST /api/runs/9/cancel': runningRun() });

    const report = within(await latestRun());
    expect(
      within(diagram()).getByRole('button', { name: /^Comparison, .*Running/ }),
    ).toBeDisabled();
    expect(screen.queryByRole('button', { name: '+ Parallel step' })).not.toBeInTheDocument();

    await userEvent.click(await report.findByRole('button', { name: 'Stop the run' }));
    expect(server.to('POST', '/api/runs/9/cancel')).toHaveLength(1);
  });

  it('answers a request the run waits on, from the report', async () => {
    const waiting = runningRun({
      status: 'waiting',
      pending_approvals: [makeApproval({ id: 31, step_order: 2 })],
    });
    const server = openBuilder(waiting, { 'POST /api/runs/9/approvals/31/approve': waiting });

    const report = within(await latestRun());
    await userEvent.click(await report.findByRole('button', { name: /Approve/ }));
    expect(server.to('POST', '/api/runs/9/approvals/31/approve')).toHaveLength(1);
  });

  it('says it is starting a run, then follows the new run', async () => {
    const start = deferred<Run>();
    openBuilder(null, { 'POST /api/pipelines/7/runs': () => start.promise });
    const run = await screen.findByRole('button', { name: 'Run Pipeline' });
    await userEvent.type(screen.getByRole('textbox', { name: /Your company/ }), 'Acme');

    await userEvent.click(run);
    expect(await screen.findByText('Starting the run…')).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Latest run' })).not.toBeInTheDocument();

    start.resolve(runningRun({ id: 10 }));
    const report = within(await latestRun());
    expect(
      await report.findByRole('heading', { level: 2, name: 'Your team is working' }),
    ).toBeInTheDocument();
    expect(screen.queryByText('Starting the run…')).not.toBeInTheDocument();
  });
});

describe('PipelineBuilderPage: before a run', () => {
  afterEach(() => vi.restoreAllMocks());

  it('adds parallel work and a following stage from the diagram', async () => {
    openBuilder();
    await screen.findByRole('heading', { level: 1, name: SAVED.name });

    await userEvent.click(within(diagram()).getAllByRole('button', { name: '+ Parallel step' })[0]);
    expect(within(diagram()).getByText('Stage 1 · parallel')).toBeInTheDocument();

    await userEvent.click(within(diagram()).getAllByRole('button', { name: '+ Next stage' })[0]);
    expect(within(diagram()).getByText('Stage 3')).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Latest run' })).not.toBeInTheDocument();
  });
});

describe('PipelineBuilderPage: where the report’s title rows stick', () => {
  afterEach(() => vi.restoreAllMocks());

  it('lets the window scroll the page below xl, so the report’s title rows can stick', async () => {
    openBuilder(finishedRun());
    const section = await latestRun();

    // A scroll container that never scrolls would hold every sticky row in place.
    const main = screen.getByRole('main');
    expect(main.classList).not.toContain('overflow-y-auto');
    expect(main.classList).toContain('xl:overflow-y-auto');
    // Below lg the 60px top bar covers the window's top; from lg up nothing does.
    expect(section.classList).toContain('[--sticky-top:60px]');
    expect(section.classList).toContain('lg:[--sticky-top:0px]');
  });

  it('keeps the scroller’s top edge free, so a title row sticks at its very top from xl', async () => {
    openBuilder(finishedRun());
    await latestRun();

    // A sticky row stops below its scroll container's top padding, and the text scrolling
    // past would show above it: the vertical padding sits inside, on the page's column.
    const main = screen.getByRole('main');
    expect([...main.classList].filter((name) => /^(\w+:)?(p|pt|py)-/.test(name))).toEqual([]);
  });
});
