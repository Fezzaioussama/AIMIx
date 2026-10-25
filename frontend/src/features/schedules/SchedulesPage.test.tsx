import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import type { Schedule } from '../../core/api/types';
import { makeRun } from '../runs/testData';
import { SCHEDULES_PATH } from './paths';
import { SchedulesPage } from './SchedulesPage';
import { NAMED_SCHEDULE, SCHEDULE, allowForSlowMachines, json, refusal, serve } from './testData';

allowForSlowMachines();

const NO_CONTENT = () => new Response(null, { status: 204 });
const LISTING = `GET ${API.schedules}`;
const PREVIEW = { [`POST ${API.previewSchedule}`]: { next_run_at: '2026-10-26T08:00:00Z' } };

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[SCHEDULES_PATH]}>
      <Routes>
        <Route path={SCHEDULES_PATH} element={<SchedulesPage />} />
        <Route path="/runs" element={<p>The run history</p>} />
        <Route path="/runs/:runId" element={<p>A run page</p>} />
        <Route path="/pipeline" element={<p>The builder</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

const card = (name: string) => screen.getByRole('region', { name });

describe('SchedulesPage', () => {
  afterEach(() => vi.restoreAllMocks());

  it('lists each schedule in words, with its next run and its last run', async () => {
    const withRun: Schedule = {
      ...SCHEDULE,
      last_run: { id: 12, status: 'succeeded', created_at: '2026-10-19T08:00:00Z' },
    };
    serve({ [LISTING]: [withRun, NAMED_SCHEDULE] });
    renderPage();

    const first = await screen.findByRole('region', { name: 'Competitor news' });
    expect(within(first).getByText('Every Monday at 09:00, Paris time')).toBeInTheDocument();
    expect(within(first).getByText('Mon 26 Oct, 09:00')).toBeInTheDocument();
    const last = within(first).getByRole('link', { name: /Open the run from/ });
    expect(last).toHaveAttribute('href', '/runs/12');
    expect(within(last).getByText('Done')).toBeInTheDocument();
    expect(within(card('Post writer')).getByText('No runs yet')).toBeInTheDocument();
    expect(within(first).getByRole('switch', { name: /Run Competitor news/ })).toBeChecked();
  });

  it('links each schedule to its pipeline', async () => {
    serve({ [LISTING]: [SCHEDULE] });
    renderPage();

    await userEvent.click(await screen.findByRole('link', { name: 'Competitor news' }));

    expect(screen.getByText('The builder')).toBeInTheDocument();
  });

  it('says plainly when a schedule is off, and when its last time could not start', async () => {
    const off: Schedule = {
      ...SCHEDULE,
      enabled: false,
      next_run_at: null,
      last_error: 'No API key is set for openrouter. Add one on the Settings page.',
    };
    serve({ [LISTING]: [off] });
    renderPage();

    const region = await screen.findByRole('region', { name: 'Competitor news' });

    // (Cards fade in, so "in the document" is what is checked, not "visible".)
    expect(
      within(region).getByText('Off. It will not run until you turn it on.'),
    ).toBeInTheDocument();
    expect(
      within(region).getByText(/it could not start: No API key is set for openrouter/),
    ).toBeInTheDocument();
    expect(within(region).getByRole('switch')).not.toBeChecked();
  });

  it('shows the two views of the Runs screen, with Schedules the current one', async () => {
    serve({ [LISTING]: [] });
    renderPage();

    const views = await screen.findByRole('navigation', { name: 'Runs views' });

    expect(within(views).getByRole('link', { name: 'Schedules' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(within(views).getByRole('link', { name: 'History' })).not.toHaveAttribute(
      'aria-current',
    );
    expect(within(views).getByRole('link', { name: 'History' })).toHaveAttribute('href', '/runs');
  });

  it('points to the builder when there is nothing scheduled yet', async () => {
    serve({ [LISTING]: [] });
    renderPage();

    expect(await screen.findByText(/No schedules yet/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Schedule this pipeline' })).toHaveAttribute(
      'href',
      '/pipeline',
    );
  });

  it('says when the schedules cannot be loaded', async () => {
    serve({ [LISTING]: refusal('Could not reach the database.', 500, 'server_error') });
    renderPage();

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not reach the database.');
  });

  it('turns a schedule off and back on', async () => {
    const off = { ...SCHEDULE, enabled: false, next_run_at: null };
    const calls = serve({
      [LISTING]: [SCHEDULE],
      [`PATCH ${API.schedule(SCHEDULE.id)}`]: ({ body }: { body: { enabled: boolean } }) =>
        body.enabled ? SCHEDULE : off,
    });
    renderPage();
    const toggle = await screen.findByRole('switch', { name: /Run Competitor news/ });

    await userEvent.click(toggle);

    expect(
      await screen.findByText(/Off\. It will not run until you turn it on\./),
    ).toBeInTheDocument();
    expect(calls.at(-1)).toMatchObject({ method: 'PATCH', body: { enabled: false } });
    expect(await screen.findByRole('status')).toHaveTextContent('Schedule turned off.');

    await userEvent.click(toggle);

    expect(await screen.findByText('Mon 26 Oct, 09:00')).toBeInTheDocument();
    expect(calls.at(-1)).toMatchObject({ body: { enabled: true } });
  });

  it('deletes a schedule only after a confirmation that starts on the safe choice', async () => {
    const calls = serve({
      [LISTING]: [SCHEDULE, NAMED_SCHEDULE],
      [`DELETE ${API.schedule(SCHEDULE.id)}`]: NO_CONTENT,
    });
    renderPage();
    const region = await screen.findByRole('region', { name: 'Competitor news' });

    await userEvent.click(within(region).getByRole('button', { name: 'Delete' }));
    const confirm = within(region).getByRole('group', { name: 'Delete this schedule?' });
    expect(within(confirm).getByRole('button', { name: 'Keep it' })).toHaveFocus();
    expect(calls.some((call) => call.method === 'DELETE')).toBe(false);

    await userEvent.click(within(confirm).getByRole('button', { name: 'Keep it' }));
    expect(within(region).queryByRole('group')).toBeNull();
    expect(within(region).getByRole('button', { name: 'Delete' })).toHaveFocus();
    expect(calls.some((call) => call.method === 'DELETE')).toBe(false);

    await userEvent.click(within(region).getByRole('button', { name: 'Delete' }));
    await userEvent.click(screen.getByRole('button', { name: 'Delete schedule' }));

    expect(await screen.findByText(/Schedule deleted\./)).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Competitor news' })).toBeNull();
    expect(screen.getByRole('region', { name: 'Post writer' })).toBeInTheDocument();
    expect(calls.at(-1)).toMatchObject({ method: 'DELETE', path: API.schedule(SCHEDULE.id) });
  });

  it('edits a schedule in place and saves only through the form', async () => {
    const edited = { ...SCHEDULE, time: '10:30', next_run_at: '2026-10-26T09:30:00Z' };
    const calls = serve({
      ...PREVIEW,
      [LISTING]: [SCHEDULE],
      [`PATCH ${API.schedule(SCHEDULE.id)}`]: edited,
    });
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: 'Edit' }));

    const form = screen.getByRole('form', { name: 'Edit the schedule of Competitor news' });
    expect(within(form).getByLabelText('Repeat')).toHaveValue('weekly');
    expect(within(form).getByLabelText('Day of the week')).toHaveValue('0');
    expect(within(form).getByLabelText('Time')).toHaveValue('09:00');
    expect(within(form).getByLabelText('Time zone')).toHaveValue('Europe/Paris');
    expect(within(form).getByRole('textbox', { name: 'Input for each scheduled run' })).toHaveValue(
      SCHEDULE.input,
    );

    const time = within(form).getByLabelText('Time');
    await userEvent.clear(time);
    await userEvent.type(time, '10:30');
    await userEvent.click(within(form).getByRole('button', { name: 'Save changes' }));

    expect(await screen.findByText('Schedule saved.')).toBeInTheDocument();
    expect(calls.find((call) => call.method === 'PATCH')).toMatchObject({
      path: API.schedule(SCHEDULE.id),
      body: {
        frequency: 'weekly',
        time: '10:30',
        weekday: 0,
        timezone: 'Europe/Paris',
        input: SCHEDULE.input,
      },
    });
    expect(screen.queryByRole('form')).toBeNull();
    expect(screen.getByText('Every Monday at 10:30, Paris time')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Edit' })).toHaveFocus();
  });

  it('edits the named inputs of a schedule by their labels', async () => {
    const calls = serve({
      ...PREVIEW,
      [LISTING]: [NAMED_SCHEDULE],
      [`PATCH ${API.schedule(NAMED_SCHEDULE.id)}`]: NAMED_SCHEDULE,
    });
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: 'Edit' }));

    const topic = screen.getByRole('textbox', { name: /Topic/ });
    expect(topic).toHaveValue('bees');
    await userEvent.clear(topic);
    await userEvent.type(topic, 'ants');
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));

    await screen.findByText('Schedule saved.');
    expect(calls.find((call) => call.method === 'PATCH')?.body).toMatchObject({
      inputs: { topic: 'ants', audience: 'kids' },
    });
  });

  it('leaves the schedule untouched when the edit is cancelled', async () => {
    const calls = serve({ ...PREVIEW, [LISTING]: [SCHEDULE] });
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: 'Edit' }));

    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(screen.queryByRole('form')).toBeNull();
    expect(calls.some((call) => call.method === 'PATCH')).toBe(false);
    expect(screen.getByRole('button', { name: 'Edit' })).toHaveFocus();
  });

  it('keeps the form open and says why when a change is refused', async () => {
    serve({
      ...PREVIEW,
      [LISTING]: [SCHEDULE],
      [`PATCH ${API.schedule(SCHEDULE.id)}`]: refusal(
        'This pipeline takes named inputs instead of text: topic.',
      ),
    });
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: 'Edit' }));

    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This pipeline takes named inputs instead of text: topic.',
    );
    expect(screen.getByRole('form')).toBeInTheDocument();
  });

  it('starts a run now and opens it', async () => {
    const run = makeRun({ id: 9, trigger: 'schedule', schedule_id: SCHEDULE.id });
    const calls = serve({
      [LISTING]: [SCHEDULE],
      [`POST ${API.runSchedule(SCHEDULE.id)}`]: json(run, 202),
    });
    renderPage();

    await userEvent.click(await screen.findByRole('button', { name: 'Run now' }));

    expect(await screen.findByText('A run page')).toBeInTheDocument();
    expect(calls.at(-1)).toMatchObject({ method: 'POST', path: API.runSchedule(SCHEDULE.id) });
  });

  it('stays on the list and says why when a run cannot start', async () => {
    serve({
      [LISTING]: [SCHEDULE],
      [`POST ${API.runSchedule(SCHEDULE.id)}`]: refusal('This pipeline has no steps to run.'),
    });
    renderPage();

    await userEvent.click(await screen.findByRole('button', { name: 'Run now' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This pipeline has no steps to run.',
    );
    expect(screen.queryByText('A run page')).toBeNull();
  });
});
