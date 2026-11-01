import { render, screen, waitFor, within } from '@testing-library/react';
import { MotionGlobalConfig } from 'motion/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Run } from '../../../core/api/types';
import { AI_NOTICE } from '../../../core/ui/AiNotice';
import { DeliverableList } from './DeliverableList';
import { reportModel } from './reportModel';
import { ENDED, stepOf, teamRun, type StepState } from './reportTestData';

const motion = vi.hoisted(() => ({ reduced: false }));

vi.mock('motion/react', async (original) => ({
  ...(await original<typeof import('motion/react')>()),
  useReducedMotion: () => motion.reduced,
}));

afterEach(() => {
  motion.reduced = false;
});

function renderList(run: Run, level: 2 | 3 = 3) {
  const list = (shown: Run) => (
    <DeliverableList run={shown} model={reportModel(shown)} level={level} />
  );
  const view = render(list(run));
  return { ...view, poll: (next: Run) => view.rerender(list(next)) };
}

function region(): HTMLElement {
  return screen.getByRole('region', { name: 'Deliverables' });
}

/** The motion wrapper a deliverable's article sits in. */
function wrapperOf(name: string): HTMLElement {
  return screen.getByRole('article', { name }).parentElement as HTMLElement;
}

/** During a hand-over both stand in the same place: the wrapper that is not `leaving`. */
function arrivingBeside(leaving: HTMLElement, name: string): HTMLElement {
  const wrappers = screen
    .getAllByRole('article', { name })
    .map((article) => article.parentElement as HTMLElement);
  const arriving = wrappers.find((wrapper) => wrapper !== leaving);
  if (arriving === undefined) throw new Error(`Nothing arrives beside ${name}.`);
  return arriving;
}

const WRITING: StepState[] = [['succeeded'], ['succeeded'], ['running'], ['pending']];
const DONE: StepState[] = [
  ['succeeded'],
  ['succeeded'],
  ['succeeded'],
  ['succeeded', { verdict: 'pass' }],
];

describe('DeliverableList', () => {
  beforeEach(() => {
    MotionGlobalConfig.skipAnimations = true;
  });
  afterEach(() => {
    MotionGlobalConfig.skipAnimations = false;
  });

  it('shows each deliverable where it will stay: a document once ready, a slot until then', () => {
    renderList(teamRun(WRITING));

    const [blog, linkedIn] = within(region()).getAllByRole('article');
    expect(blog).toHaveAccessibleName('Blog post');
    expect(within(blog).getByRole('heading', { level: 3, name: 'Blog post' })).toHaveAttribute(
      'tabindex',
      '-1',
    );
    expect(within(blog).getByText('Blog post text')).toBeInTheDocument();
    expect(within(blog).getByRole('button', { name: 'Copy Blog post as formatted text' }));
    expect(linkedIn).toHaveAccessibleName('LinkedIn post');
    expect(within(linkedIn).getByText('Being written')).toBeInTheDocument();
    // The research notes are the team's own work: never one of the deliverables.
    expect(within(region()).queryByText('Research text')).not.toBeInTheDocument();
    expect(within(region()).queryByRole('article', { name: 'Final check' })).toBeNull();
  });

  it('leads in with the AI notice once, as soon as an agent has written something', () => {
    const { poll } = renderList(teamRun([['pending'], ['pending'], ['pending'], ['pending']]));
    expect(screen.queryByText(AI_NOTICE)).not.toBeInTheDocument();

    poll(teamRun([['succeeded'], ['running'], ['running'], ['pending']]));

    expect(within(region()).getAllByText(AI_NOTICE)).toHaveLength(1);
  });

  it('renders nothing for a run without deliverables yet', () => {
    const { container } = renderList(teamRun([], { steps: [] }));

    expect(container).toBeEmptyDOMElement();
  });

  it('nests the text’s own headings under the title, one level per level', () => {
    const run = teamRun(DONE, { status: 'succeeded', ...ENDED });
    stepOf(run, 2).output = '# Launch\n\n## Why now\n\nBecause.';

    const { unmount } = renderList(run, 3);
    const blog = screen.getByRole('article', { name: 'Blog post' });
    expect(within(blog).getByRole('heading', { level: 4, name: 'Launch' })).toBeInTheDocument();
    expect(within(blog).getByRole('heading', { level: 5, name: 'Why now' })).toBeInTheDocument();
    unmount();

    renderList(run, 2);
    expect(screen.getByRole('heading', { level: 2, name: 'Blog post' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 4, name: 'Why now' })).toBeInTheDocument();
  });

  it('says who wrote it, on which model and at what cost, how long it is and whether it was checked', () => {
    const run = teamRun(DONE, { status: 'succeeded', ...ENDED });
    Object.assign(stepOf(run, 2), {
      model: 'meta/llama-4-maverick',
      input_tokens: 1000,
      output_tokens: 200,
      cost_usd: 0.0012,
    });

    renderList(run);

    const blog = screen.getByRole('article', { name: 'Blog post' });
    // "Blog post text": 3 words, 14 characters, then the check's verdict. The token counts
    // are read out after the cost.
    expect(within(blog).getByText(/^by Writer · llama-4-maverick · /)).toHaveTextContent(
      'by Writer · llama-4-maverick · $0.0012 (1,000 tokens in, 200 out) · 3 words · 14 characters · Approved by the Orchestrator',
    );
    expect(within(blog).getByText('$0.0012')).toHaveAttribute('title', '1,000 tokens in, 200 out');
    expect(within(blog).getByText('Approved by the Orchestrator')).toHaveClass('text-emerald-300');
  });

  it('grounds the title row only while it is stuck, so no band sits on the page at rest', () => {
    renderList(teamRun(DONE, { status: 'succeeded', ...ENDED }));

    // jsdom cannot stick a row; Chromium measured the ground at opacity 0 at rest and 1 stuck.
    const row = screen.getByRole('heading', { name: 'Blog post' }).parentElement as HTMLElement;
    expect(row).toHaveClass('sticky', '[container-type:scroll-state]', 'before:bg-ground/90');
    expect(row).toHaveClass('[@container_not_scroll-state(stuck:top)]:before:opacity-0');
    // On a phone the stuck ground reaches into the 16px gutters, so no darker box sits on
    // the page's glow beside it.
    expect(row).toHaveClass('max-sm:before:-inset-x-4');
  });

  it('counts no characters for a text of 300 words or more, and no cost before any use', () => {
    const run = teamRun(DONE, { status: 'succeeded', ...ENDED });
    stepOf(run, 2).output = 'word '.repeat(300);

    renderList(run);

    const byline = within(screen.getByRole('article', { name: 'Blog post' })).getByText(
      /^by Writer/,
    );
    expect(byline).toHaveTextContent(
      /^by Writer · writer · 300 words · Approved by the Orchestrator$/,
    );
  });

  it('says when an agent finished without writing anything, with nothing to copy', () => {
    const run = teamRun(DONE, { status: 'succeeded', ...ENDED });
    stepOf(run, 2).output = '  ';

    renderList(run);

    const blog = screen.getByRole('article', { name: 'Blog post' });
    expect(within(blog).getByText('This agent finished without writing anything.'));
    expect(within(blog).queryByRole('button', { name: /Copy/ })).toBeNull();
    expect(within(blog).queryByText(/words/)).toBeNull();
  });

  it('turns a document sent back by the check into a slot again', async () => {
    const { poll } = renderList(teamRun(DONE.slice(0, 3).concat([['running']])));
    expect(screen.getByRole('article', { name: 'Blog post' })).toHaveTextContent('Blog post text');

    poll(teamRun([...DONE.slice(0, 3), ['succeeded', { verdict: 'revise' }]]));

    const revised = await screen.findAllByText('Being revised · round 2 of 3');
    expect(revised.map((words) => words.closest('article'))).toEqual([
      screen.getByRole('article', { name: 'Blog post' }),
      screen.getByRole('article', { name: 'LinkedIn post' }),
    ]);
  });
});

describe('DeliverableList hand-over (M5)', () => {
  /** LinkedIn post writing, then ready with `output`. */
  async function handOver(output: string): Promise<HTMLElement> {
    const { poll } = renderList(teamRun(WRITING));
    const slot = wrapperOf('LinkedIn post');

    poll(teamRun([['succeeded'], ['succeeded'], ['succeeded', { output }], ['pending']]));

    // The slot leaves through a 2px blur while the document arrives in its place. Both
    // are waited for: on a busy machine the first frame may show the blur at full opacity.
    await waitFor(() => {
      expect(slot.style.filter).toMatch(/blur/);
      expect(Number(slot.style.opacity)).toBeLessThan(1);
    });
    return arrivingBeside(slot, 'LinkedIn post');
  }

  it('brings a short document up out of a blur, and leaves no filter behind', async () => {
    const doc = await handOver('A short post.');

    expect(doc.style.transform).toMatch(/translateY/);
    expect(doc.style.filter).toMatch(/blur/);
    await waitFor(() => expect(doc.style.filter).toBe('none'), { timeout: 2000 });
    expect(Number(doc.style.opacity)).toBe(1);
  });

  it('never blurs a long document: it only rises and fades in', async () => {
    const doc = await handOver('word '.repeat(400));

    expect(doc.style.transform).toMatch(/translateY/);
    expect(doc.style.filter).toBe('');
    await waitFor(() => expect(Number(doc.style.opacity)).toBe(1), { timeout: 2000 });
  });

  it('only fades under reduced motion: nothing rises or blurs', async () => {
    motion.reduced = true;
    const { poll } = renderList(teamRun(WRITING));
    const slot = wrapperOf('LinkedIn post');

    poll(teamRun([['succeeded'], ['succeeded'], ['succeeded'], ['pending']]));

    await waitFor(() => expect(Number(slot.style.opacity)).toBeLessThan(1));
    expect(slot.style.filter).toBe('');
    const doc = arrivingBeside(slot, 'LinkedIn post');
    expect(doc.style.transform).toBe('');
    expect(doc.style.filter).toBe('');
    await waitFor(() => expect(Number(doc.style.opacity)).toBe(1));
  });

  it('does not animate what is already there when the list first appears', () => {
    renderList(teamRun(DONE, { status: 'succeeded', ...ENDED }));

    const doc = wrapperOf('Blog post');
    expect(doc.style.opacity).not.toBe('0');
    expect(doc.style.transform).not.toMatch(/translate/);
  });
});
