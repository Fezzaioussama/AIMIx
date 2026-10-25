import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import type { Pipeline } from '../../core/api/types';
import { SchedulePanel, type SchedulePanelProps } from './SchedulePanel';
import { SCHEDULE, allowForSlowMachines, json, refusal, serve } from './testData';
import { PREVIEW_DELAY_MS } from './useSchedulePreview';

allowForSlowMachines();

const PIPELINE: Pipeline = { id: 3, name: 'Competitor news', inputs: [], steps: [] };
const NAMED: Pipeline = {
  ...PIPELINE,
  inputs: [
    { name: 'topic', label: 'Topic', description: 'What to write about' },
    { name: 'audience', label: '', description: '' },
  ],
};
const PREVIEW = { [`POST ${API.previewSchedule}`]: { next_run_at: '2026-10-26T08:00:00Z' } };

function renderPanel(props: Partial<SchedulePanelProps> = {}) {
  const panel = (more: Partial<SchedulePanelProps>) => (
    <MemoryRouter>
      <SchedulePanel pipeline={PIPELINE} dirty={false} {...props} {...more} />
    </MemoryRouter>
  );
  const view = render(panel({}));
  return { rerender: (more: Partial<SchedulePanelProps>) => view.rerender(panel(more)) };
}

const toggle = () => screen.getByRole('button', { name: 'Schedule this pipeline' });
const submit = () => screen.getByRole('button', { name: 'Schedule it' });
const textBox = () => screen.getByRole('textbox', { name: 'Input for each scheduled run' });

async function openPanel() {
  await userEvent.click(toggle());
}

/** Puts a sentence in the input in one step: typing it key by key is slow when the machine is busy. */
async function enter(text: string) {
  await userEvent.click(textBox());
  await userEvent.paste(text);
}

describe('SchedulePanel', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('starts folded and builds nothing until it is opened', async () => {
    renderPanel();
    expect(toggle()).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByLabelText('Repeat')).toBeNull();

    await openPanel();

    expect(toggle()).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByLabelText('Repeat')).toBeInTheDocument();
  });

  it('asks the server nothing on a page where it is never opened', () => {
    vi.useFakeTimers();
    const calls = serve(PREVIEW);
    renderPanel();

    act(() => void vi.advanceTimersByTime(PREVIEW_DELAY_MS * 5));

    expect(calls).toEqual([]);
  });

  it('says to save an unsaved pipeline first', async () => {
    renderPanel({ pipeline: { ...PIPELINE, id: undefined } });

    await openPanel();

    expect(screen.getByText('Save this pipeline first, then you can schedule it.')).toBeVisible();
    expect(screen.queryByLabelText('Repeat')).toBeNull();
  });

  it('schedules the pipeline, saying when it runs, and starts a fresh form', async () => {
    const calls = serve({ ...PREVIEW, [`POST ${API.schedules}`]: SCHEDULE });
    renderPanel();
    await openPanel();
    await userEvent.selectOptions(screen.getByLabelText('Time zone'), 'Europe/Paris');

    expect(await screen.findByText('Every Monday at 09:00, Paris time')).toBeInTheDocument();
    expect(await screen.findByText('Next run: Mon 26 Oct, 09:00')).toBeInTheDocument();
    await enter('Research my competitors’ news');
    await userEvent.click(submit());

    const created = calls.find((call) => call.path === API.schedules);
    expect(created).toMatchObject({
      method: 'POST',
      body: {
        pipeline_id: 3,
        frequency: 'weekly',
        time: '09:00',
        weekday: 0,
        timezone: 'Europe/Paris',
        input: 'Research my competitors’ news',
      },
    });
    expect(
      await screen.findByText(
        'Scheduled: Every Monday at 09:00, Paris time. Next run: Mon 26 Oct, 09:00.',
      ),
    ).toBeInTheDocument();
    expect(textBox()).toHaveValue('');
    expect(screen.getByRole('link', { name: 'See all your schedules' })).toHaveAttribute(
      'href',
      '/runs/schedules',
    );
  });

  it('shows only the fields the chosen frequency needs', async () => {
    serve(PREVIEW);
    renderPanel();
    await openPanel();
    expect(screen.getByLabelText('Day of the week')).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText('Repeat'), 'monthly');
    expect(screen.queryByLabelText('Day of the week')).toBeNull();
    await userEvent.selectOptions(screen.getByLabelText('Day of the month'), '31');
    expect(screen.getByText('In a shorter month it runs on the last day.')).toBeInTheDocument();
    expect(await screen.findByText(/On the 31st of every month at 09:00/)).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText('Repeat'), 'hourly');
    expect(screen.queryByLabelText('Day of the month')).toBeNull();
    expect(screen.queryByLabelText('Time')).toBeNull();
    await userEvent.selectOptions(screen.getByLabelText('Minutes past the hour'), '15');
    expect(await screen.findByText('Every hour, 15 minutes past')).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText('Repeat'), 'daily');
    expect(screen.getByLabelText('Time')).toHaveValue('09:00');
  });

  it('asks the server about each timing it shows', async () => {
    const calls = serve(PREVIEW);
    renderPanel();
    await openPanel();

    await userEvent.selectOptions(screen.getByLabelText('Time zone'), 'Asia/Tokyo');
    // The words follow at once; the next run (08:00 UTC is 17:00 in Tokyo) once it is worked out.
    expect(screen.getByText('Every Monday at 09:00, Tokyo time')).toBeInTheDocument();
    expect(screen.getByText('Working out the next run…')).toBeInTheDocument();
    await screen.findByText('Next run: Mon 26 Oct, 17:00');

    const last = calls.filter((call) => call.path === API.previewSchedule).at(-1);
    expect(last?.body).toEqual({
      frequency: 'weekly',
      time: '09:00',
      weekday: 0,
      timezone: 'Asia/Tokyo',
    });
  });

  it('asks for what each run is given before saving, and sends nothing without it', async () => {
    const calls = serve(PREVIEW);
    renderPanel();
    await openPanel();

    await userEvent.click(submit());

    expect(screen.getByRole('alert')).toHaveTextContent('Say what each run should work on.');
    expect(calls.filter((call) => call.method === 'POST' && call.path === API.schedules)).toEqual(
      [],
    );
  });

  it('asks for each named input of the pipeline, and sends their values', async () => {
    const calls = serve({ ...PREVIEW, [`POST ${API.schedules}`]: SCHEDULE });
    renderPanel({ pipeline: NAMED });
    await openPanel();
    expect(screen.getByPlaceholderText('What to write about')).toBeInTheDocument();

    await userEvent.type(screen.getByRole('textbox', { name: /Topic/ }), 'bees');
    await userEvent.click(submit());
    expect(screen.getByRole('alert')).toHaveTextContent('Fill in audience.');

    await userEvent.type(screen.getByRole('textbox', { name: /audience/ }), 'kids');
    await userEvent.click(submit());

    const created = calls.find((call) => call.path === API.schedules);
    expect(created?.body).toMatchObject({ inputs: { topic: 'bees', audience: 'kids' } });
    expect(created?.body).not.toHaveProperty('input');
  });

  it('asks for a time of day, and does not guess a next run without one', async () => {
    const calls = serve(PREVIEW);
    renderPanel();
    await openPanel();
    await screen.findByText(/Next run:/);
    const asked = calls.length;

    await userEvent.clear(screen.getByLabelText('Time'));
    await userEvent.type(textBox(), 'go');
    await userEvent.click(submit());

    expect(screen.getByText('Choose a time to see when it runs.')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('Choose a time of day.');
    expect(calls).toHaveLength(asked);
  });

  it('waits for saved changes, because a schedule runs the saved version', async () => {
    serve(PREVIEW);
    renderPanel({ dirty: true });
    await openPanel();

    expect(submit()).toBeDisabled();
    expect(
      screen.getByText('Save your changes first: a schedule runs the saved version.'),
    ).toBeInTheDocument();
  });

  it('shows why the server refused, and keeps what was typed', async () => {
    serve({
      ...PREVIEW,
      [`POST ${API.schedules}`]: refusal('You can have up to 20 schedules. Delete one first.'),
    });
    renderPanel();
    await openPanel();
    await userEvent.type(textBox(), 'go');

    await userEvent.click(submit());

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'You can have up to 20 schedules. Delete one first.',
    );
    expect(textBox()).toHaveValue('go');
    expect(submit()).toBeEnabled();
  });

  it('is busy while saving, so it cannot be pressed twice', async () => {
    let answer: (response: Response) => void = () => {};
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (path) =>
      String(path) === API.previewSchedule
        ? json({ next_run_at: '2026-10-26T08:00:00Z' })
        : new Promise<Response>((resolve) => (answer = resolve)),
    );
    renderPanel();
    await openPanel();
    await userEvent.type(textBox(), 'go');

    await userEvent.click(submit());

    const saving = screen.getByRole('button', { name: 'Saving…' });
    expect(saving).toBeDisabled();
    await act(async () => answer(json(SCHEDULE, 201)));
    expect(await screen.findByText(/^Scheduled: /)).toBeInTheDocument();
  });

  it('starts afresh for another pipeline', async () => {
    serve({ ...PREVIEW, [`POST ${API.schedules}`]: SCHEDULE });
    const { rerender } = renderPanel();
    await openPanel();
    await userEvent.type(textBox(), 'go');
    await userEvent.click(submit());
    await screen.findByText(/^Scheduled: /);

    rerender({ pipeline: { ...PIPELINE, id: 8 } });

    expect(toggle()).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText(/^Scheduled: /)).toBeNull();
  });
});
