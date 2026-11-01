import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ExtractedDocument } from '../../core/api/types';
import { ComposerAttachments } from './ComposerAttachments';
import type { PendingDocument } from './missionDocuments';
import type { MissionDocuments } from './useMissionDocuments';

// The person's motion preference, as motion/react reads it; each test sets its own.
const preference = vi.hoisted(() => ({ reduced: false }));
vi.mock('motion/react', async (importOriginal) => ({
  ...(await importOriginal<typeof import('motion/react')>()),
  useReducedMotion: () => preference.reduced,
}));

const WIKI = 'https://en.wikipedia.org/wiki/Retrieval-augmented_generation';
const LONG_NAME = 'quarterly-board-report-final-version-2026-with-appendix.pdf';

function readChip(kind: PendingDocument['kind'], document: ExtractedDocument): PendingDocument {
  const source = document.filename;
  return { id: source, kind, source, key: source, state: 'read', document };
}

const page = readChip('link', {
  filename: WIKI,
  format: 'html',
  text: 'Page text.',
  characters: 24468,
  pages: null,
  truncated: false,
});

const report: ExtractedDocument = {
  filename: 'b_long45.pdf',
  format: 'pdf',
  text: 'Report text.',
  characters: 116049,
  pages: 45,
  truncated: true,
};
const longPdf = readChip('file', report);
const namedAtLength = readChip('file', { ...report, filename: LONG_NAME });

function documentsOf(items: PendingDocument[]): MissionDocuments {
  return {
    items,
    read: [],
    reading: '',
    full: false,
    notice: '',
    status: '',
    addFiles: vi.fn(),
    addLink: vi.fn(),
    remove: vi.fn(),
    release: vi.fn(),
  };
}

function Attachments({ items }: { items: PendingDocument[] }) {
  return (
    <ComposerAttachments
      documents={documentsOf(items)}
      hasTeam={false}
      placement={null}
      onEmptied={vi.fn()}
    />
  );
}

const list = () => screen.getByRole('list', { name: 'Attached documents' });

afterEach(() => {
  preference.reduced = false;
});

describe('ComposerAttachments chips', () => {
  it('shows a link’s shortened label whole, with the full address in its title', () => {
    render(<Attachments items={[page]} />);

    // linkLabel already cut it in the middle: the chip does not cut it a second time.
    const name = screen.getByText('en.wikipedia.org/wiki/Re…al-augmented_generation');
    expect(name).toHaveAttribute('title', WIKI);
    expect(name).not.toHaveClass('truncate');
  });

  it('cuts a long file name in one place, its end, with the whole name in its title', () => {
    render(<Attachments items={[namedAtLength]} />);

    const name = screen.getByText(LONG_NAME);
    expect(name).toHaveAttribute('title', LONG_NAME);
    expect(name).toHaveClass('truncate');
  });

  it('keeps × in its own column, at the top right, however the details wrap', () => {
    render(<Attachments items={[longPdf]} />);

    const chip = within(list()).getByRole('listitem');
    const remove = within(chip).getByRole('button', { name: 'Remove b_long45.pdf' });
    const details = within(chip).getByText(
      '45 pages · 116,049 characters · part of it was left out',
    );
    // The name and its details wrap inside their own column; × is the chip's last column.
    expect(chip).toHaveClass('grid', 'items-start');
    expect(details.parentElement).not.toBe(chip);
    expect(within(details.parentElement as HTMLElement).getByText('b_long45.pdf')).toBeDefined();
    expect(remove.parentElement).toBe(chip);
  });

  it('caps the chips’ height on a short screen and scrolls them; the keyboard reaches each', async () => {
    const user = userEvent.setup();
    render(<Attachments items={[longPdf, page, namedAtLength]} />);

    expect(list()).toHaveClass('overflow-y-auto');
    expect(list().className).toMatch(/max-h-\[/);
    // Focus scrolls a chip hidden below the cap into view, as for any focused control.
    for (const name of ['b_long45.pdf', 'en.wikipedia.org/wiki/Re…al-augmented_generation']) {
      await user.tab();
      expect(screen.getByRole('button', { name: `Remove ${name}` })).toHaveFocus();
    }
    await user.tab();
    expect(screen.getByRole('button', { name: `Remove ${LONG_NAME}` })).toHaveFocus();
  });
});

describe('ComposerAttachments motion', () => {
  it('brings a new chip in with a slight scale and blur', () => {
    const { rerender } = render(<Attachments items={[]} />);

    rerender(<Attachments items={[longPdf]} />);

    const chip = within(list()).getByRole('listitem');
    expect(chip.style.filter).toBe('blur(2px)');
    expect(chip.style.opacity).toBe('0');
  });

  it('only fades a new chip in under reduced motion: no blur, no scale', () => {
    preference.reduced = true;
    const { rerender } = render(<Attachments items={[]} />);

    rerender(<Attachments items={[longPdf]} />);

    const chip = within(list()).getByRole('listitem');
    expect(chip.style.opacity).toBe('0');
    expect(chip.style.filter).toBe('');
    expect(chip.style.transform).toBe('');
  });
});
