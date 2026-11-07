/**
 * What the RunReport specs share: the report rendered in a router with controls that
 * record their calls, the server's file listing stubbed, and a run whose agents have roles.
 */
import { render, screen, within } from '@testing-library/react';
import { MotionGlobalConfig } from 'motion/react';
import { MemoryRouter } from 'react-router-dom';
import { afterAll, afterEach, beforeAll, beforeEach, vi } from 'vitest';

import type { Run } from '../../../core/api/types';
import { json, makeRun } from '../testData';
import type { RunControls } from '../useRun';
import { RunReport, type ReportExtras } from './RunReport';

/** No file in the workspace: "Saved during this run" stays out of the way. */
const NO_FILES = {
  files: [],
  used_bytes: 0,
  quota_bytes: 1,
  max_file_bytes: 1,
  allowed_extensions: [],
};

/**
 * Motion off for the report specs only (not globally), and the server's file listing
 * stubbed; a spec may stub fetch again for its own answers.
 */
export function useReportSpec(): void {
  beforeAll(() => {
    MotionGlobalConfig.skipAnimations = true;
  });
  afterAll(() => {
    MotionGlobalConfig.skipAnimations = false;
  });
  beforeEach(() => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => json(NO_FILES));
  });
  afterEach(() => vi.restoreAllMocks());
}

export function controls(overrides: Partial<RunControls> = {}): RunControls {
  return {
    stop: vi.fn(async () => {}),
    resume: vi.fn(async () => {}),
    approve: vi.fn(async () => {}),
    decline: vi.fn(async () => {}),
    answer: vi.fn(async () => {}),
    rate: vi.fn(async () => {}),
    busy: false,
    error: '',
    ...overrides,
  };
}

interface ReportOptions {
  control?: RunControls;
  level?: 2 | 3;
  extras?: ReportExtras;
}

/** The report of `run`, and a way to show the next poll of it in place. */
export function renderReport(run: Run, options: ReportOptions = {}) {
  const control = options.control ?? controls();
  const report = (shown: Run, next: RunControls = control) => (
    <MemoryRouter>
      <RunReport
        key={shown.id}
        run={shown}
        control={next}
        level={options.level ?? 3}
        extras={options.extras}
      />
    </MemoryRouter>
  );
  const view = render(report(run));
  return {
    ...view,
    control,
    poll: (next: Run, nextControl?: RunControls) => view.rerender(report(next, nextControl)),
  };
}

/** makeRun's team (Research, then Draft and Summary at once), its agents with roles. */
export function teamWithRoles(overrides: Partial<Run> = {}): Run {
  const steps = makeRun().definition.steps.map((step) => ({
    ...step,
    role: step.order === 1 ? 'Researcher' : 'Writer',
  }));
  return makeRun({ definition: { name: 'Launch kit', inputs: [], steps }, ...overrides });
}

export function deliverablesRegion(): HTMLElement {
  return screen.getByRole('region', { name: 'Deliverables' });
}

/** "How your team got there": its section, opened. */
export function appendix(): HTMLElement {
  const toggle = screen.getByRole('button', { name: /How your team got there/ });
  return toggle.closest('section') as HTMLElement;
}

/** The report's own polite announcer, straight under body. */
export function announcer(): HTMLElement {
  const own = screen
    .getAllByRole('status')
    .find((element) => element.parentElement === document.body);
  if (own === undefined) throw new Error('The report has no announcer.');
  return own;
}

export function inDeliverables(text: string | RegExp): HTMLElement {
  return within(deliverablesRegion()).getByText(text);
}
