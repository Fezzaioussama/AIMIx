import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MotionGlobalConfig } from 'motion/react';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import { saveBlob } from '../../../core/saveBlob';
import { DeliverableDoc } from './DeliverableDoc';
import { reportModel } from './reportModel';
import { ENDED, stepOf, teamRun } from './reportTestData';

vi.mock('../../../core/saveBlob', () => ({ saveBlob: vi.fn() }));

beforeAll(() => {
  MotionGlobalConfig.skipAnimations = true;
});
afterAll(() => {
  MotionGlobalConfig.skipAnimations = false;
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  Reflect.deleteProperty(navigator, 'clipboard');
});

/** jsdom has no ClipboardItem: this one keeps what it was given. */
class FakeClipboardItem {
  constructor(readonly items: Record<string, Blob>) {}
}

/** jsdom's Blob has no text(); FileReader reads it. */
function textOf(blob: Blob): Promise<string> {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.readAsText(blob);
  });
}

/** A finished run whose Blog post is "Draft", written in Markdown. */
function renderDraft() {
  const run = teamRun(
    [['succeeded'], ['succeeded'], ['succeeded'], ['succeeded', { verdict: 'pass' }]],
    { status: 'succeeded', ...ENDED },
  );
  const step = stepOf(run, 2);
  step.title = 'Draft';
  step.output = '# Plan\n\n**Bold** launch with *care*.\n\n- one\n- two';
  const view = reportModel(run).deliverables[0];
  return render(<DeliverableDoc run={run} view={view} check={null} level={3} />);
}

function copyButton(): HTMLElement {
  return screen.getByRole('button', { name: 'Copy Draft as formatted text' });
}

describe('DeliverableActions: Copy', () => {
  it('copies the text formatted and as plain text, then says so', async () => {
    const write = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    Object.defineProperty(navigator, 'clipboard', {
      value: { write, writeText: vi.fn() },
      configurable: true,
    });
    vi.stubGlobal('ClipboardItem', FakeClipboardItem);
    renderDraft();

    await user.click(copyButton());

    const [[items]] = write.mock.calls as [[FakeClipboardItem[]]];
    const html = await textOf(items[0].items['text/html']);
    const plain = await textOf(items[0].items['text/plain']);
    expect(html).toContain('<strong>Bold</strong>');
    expect(html).toContain('<h1>Plan</h1>');
    expect(plain).toBe('Plan\n\nBold launch with care.\n\n• one\n• two');
    expect(plain).not.toMatch(/\*\*|#/);
    await waitFor(() => expect(copyButton()).toHaveAttribute('data-copied', 'true'));
    expect(screen.getByRole('status')).toHaveTextContent('Draft copied.');
    expect(screen.getByRole('status')).toHaveClass('sr-only');
  });

  it('copies the plain text where the browser has no rich clipboard', async () => {
    const user = userEvent.setup();
    renderDraft();

    await user.click(copyButton());

    expect(await navigator.clipboard.readText()).toBe(
      'Plan\n\nBold launch with care.\n\n• one\n• two',
    );
  });

  it('says so, visibly, when the browser refuses to copy', async () => {
    const user = userEvent.setup();
    Object.defineProperty(navigator, 'clipboard', {
      value: {
        write: vi.fn().mockRejectedValue(new Error('denied')),
        writeText: vi.fn().mockRejectedValue(new Error('denied')),
      },
      configurable: true,
    });
    vi.stubGlobal('ClipboardItem', FakeClipboardItem);
    renderDraft();

    await user.click(copyButton());

    const status = screen.getByRole('status');
    await waitFor(() =>
      expect(status).toHaveTextContent('Could not copy. Select the text and copy it yourself.'),
    );
    expect(status).not.toHaveClass('sr-only');
    expect(status).toHaveClass('text-amber-300');
    expect(copyButton()).toHaveAttribute('data-copied', 'false');
  });

  it('keeps Copy and Copied in one cell, so the button keeps its width', () => {
    renderDraft();

    const copy = within(copyButton()).getByText('Copy');
    const copied = within(copyButton()).getByText('Copied');
    expect(copy.parentElement).toBe(copied.parentElement);
    expect(copy).toHaveClass('col-start-1', 'row-start-1', 'opacity-100');
    expect(copied).toHaveClass('col-start-1', 'row-start-1', 'opacity-0');
  });
});

describe('DeliverableActions: Download', () => {
  function downloadButton(): HTMLElement {
    return screen.getByRole('button', { name: 'Download Draft' });
  }

  async function savedAs(format: RegExp): Promise<[Blob, string]> {
    const user = userEvent.setup();
    renderDraft();
    await user.click(downloadButton());
    await user.click(screen.getByRole('button', { name: format }));
    expect(saveBlob).toHaveBeenCalledTimes(1);
    return vi.mocked(saveBlob).mock.calls[0];
  }

  it('opens the formats in a group under Download', async () => {
    const user = userEvent.setup();
    renderDraft();
    expect(downloadButton()).toHaveAttribute('aria-expanded', 'false');

    await user.click(downloadButton());

    const menu = screen.getByRole('group', { name: 'Download Draft as' });
    expect(downloadButton()).toHaveAttribute('aria-expanded', 'true');
    expect(downloadButton()).toHaveAttribute('aria-controls', menu.id);
    expect(
      within(menu)
        .getAllByRole('button')
        .map((option) => option.textContent),
    ).toEqual([
      'Formatted (.html)Opens in Word, Google Docs or a browser',
      'Plain text (.txt)',
      'Markdown (.md)',
    ]);
  });

  it('closes on Escape and gives the focus back to Download', async () => {
    const user = userEvent.setup();
    renderDraft();
    await user.click(downloadButton());
    await user.tab();
    expect(screen.getByRole('button', { name: /Formatted/ })).toHaveFocus();

    await user.keyboard('{Escape}');

    await waitFor(() => expect(screen.queryByRole('group')).not.toBeInTheDocument());
    expect(downloadButton()).toHaveFocus();
    expect(downloadButton()).toHaveAttribute('aria-expanded', 'false');
  });

  it('closes on a press outside, the focus going back to Download', async () => {
    const user = userEvent.setup();
    renderDraft();
    await user.click(downloadButton());

    await user.click(screen.getByText('Bold'));

    await waitFor(() => expect(screen.queryByRole('group')).not.toBeInTheDocument());
    await waitFor(() => expect(downloadButton()).toHaveFocus());
  });

  it('saves the formatted file under the title, then closes and refocuses Download', async () => {
    const [blob, name] = await savedAs(/Formatted \(\.html\)/);

    expect(name).toBe('Draft.html');
    expect(blob.type).toBe('text/html');
    const html = await textOf(blob);
    expect(html).toMatch(/^<!doctype html><meta charset="utf-8"><title>Draft<\/title>/);
    expect(html).toContain('<strong>Bold</strong>');
    await waitFor(() => expect(screen.queryByRole('group')).not.toBeInTheDocument());
    expect(downloadButton()).toHaveFocus();
  });

  it('saves plain text without Markdown marks', async () => {
    const [blob, name] = await savedAs(/Plain text/);

    expect(name).toBe('Draft.txt');
    expect(blob.type).toBe('text/plain');
    expect(await textOf(blob)).toBe('Plan\n\nBold launch with care.\n\n• one\n• two');
  });

  it('saves the Markdown as written', async () => {
    const [blob, name] = await savedAs(/Markdown/);

    expect(name).toBe('Draft.md');
    expect(blob.type).toBe('text/markdown');
    expect(await textOf(blob)).toBe('# Plan\n\n**Bold** launch with *care*.\n\n- one\n- two');
  });

  it('closes again from Download itself', async () => {
    const user = userEvent.setup();
    renderDraft();
    await user.click(downloadButton());

    await user.click(downloadButton());

    await waitFor(() => expect(screen.queryByRole('group')).not.toBeInTheDocument());
    expect(saveBlob).not.toHaveBeenCalled();
  });
});
