import { AlignLeft, FileText, Globe, Link2, TriangleAlert, type LucideIcon } from 'lucide-react';
import { useMemo } from 'react';

import type { Run } from '../../../core/api/types';
import { FOCUS_RING } from '../../../core/ui/focus';
import { Heading, type HeadingLevel } from '../../../core/ui/Heading';
import { countOf, formatCount } from '../../../core/usageFormat';
import { joinWords } from '../../pipelines/revision';
import {
  givenParts,
  givenSummary,
  type GivenKind,
  type GivenPart,
  type Note,
  type NoteKind,
} from './runGiven';

/** The header names this many of what was given, then counts the rest. */
const NAMED_MAX = 3;
/** The appendix shows this much of each part's text. */
const EXCERPT_CHARS = 2000;

interface Look {
  Icon: LucideIcon;
  className: string;
}

const WARNING: Look = { Icon: TriangleAlert, className: 'text-amber-300' };

/** How each note looks: amber when something may be missing, quiet for a bare link. */
const NOTE_LOOK: Record<NoteKind, Look> = {
  truncated: WARNING,
  unread: WARNING,
  thin: WARNING,
  link: { Icon: Link2, className: 'text-slate-400' },
};

function NoteLine({ note }: { note: Note }) {
  const look = NOTE_LOOK[note.kind];
  return (
    <p className={`mt-1 flex items-start gap-1.5 text-sm break-words ${look.className}`}>
      <look.Icon aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
      <span className="min-w-0">{note.words}</span>
    </p>
  );
}

/** "brief.pdf, example.com/launch, notes.docx and 2 more". */
function namesWords(names: string[]): string {
  if (names.length <= NAMED_MAX) return joinWords(names);
  return joinWords([...names.slice(0, NAMED_MAX), `${names.length - NAMED_MAX} more`]);
}

/**
 * "Given to your team: brief.pdf and example.com/launch.", in the outcome header, with
 * a note on anything that may be missing from them. Nothing when only text was typed.
 */
export function GivenLine({ run }: { run: Run }) {
  const parts = useMemo(() => givenParts(run), [run]);
  const names = givenSummary(parts);
  if (names.length === 0) return null;
  return (
    <div className="mt-3 text-sm text-slate-300">
      <p className="text-pretty break-words">Given to your team: {namesWords(names)}.</p>
      {parts
        .flatMap((part) => part.notes)
        .map((note, index) => (
          <NoteLine key={`${index}-${note.words}`} note={note} />
        ))}
    </div>
  );
}

/** Each kind of part: its icon, and how its kind and size read. */
const KIND_LOOK: Record<GivenKind, { Icon: LucideIcon; words: (characters: number) => string }> = {
  text: { Icon: AlignLeft, words: (characters) => countOf(characters, 'character') },
  document: {
    Icon: FileText,
    words: (characters) => `Document · ${countOf(characters, 'character')}`,
  },
  page: { Icon: Globe, words: (characters) => `Web page · ${countOf(characters, 'character')}` },
  link: { Icon: Link2, words: () => 'Link' },
};

/** The start of a part's text, scrollable, with how much of it is shown. */
function Excerpt({ part }: { part: GivenPart }) {
  return (
    <dd>
      <div
        role="group"
        aria-label={part.name}
        tabIndex={0}
        className={`mt-2 max-h-48 overflow-auto rounded-lg bg-slate-950/50 p-3 text-sm break-words whitespace-pre-wrap text-slate-300 ${FOCUS_RING}`}
      >
        {part.text.slice(0, EXCERPT_CHARS)}
      </div>
      {part.characters > EXCERPT_CHARS && (
        <p className="mt-1 text-xs text-slate-400">
          Showing the first {formatCount(EXCERPT_CHARS)} of {countOf(part.characters, 'character')}.
        </p>
      )}
    </dd>
  );
}

function GivenItem({ part }: { part: GivenPart }) {
  const look = KIND_LOOK[part.kind];
  return (
    <div className="py-3">
      <dt className="flex items-start gap-2 text-sm font-medium text-slate-100">
        <look.Icon aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-sky-300" />
        <span className="min-w-0 break-words">{part.name}</span>
      </dt>
      <dd className="mt-0.5 pl-6 text-xs text-slate-400 tabular-nums">
        {look.words(part.characters)}
      </dd>
      {part.notes.map((note, index) => (
        <dd key={`${index}-${note.words}`} className="pl-6">
          <NoteLine note={note} />
        </dd>
      ))}
      {part.kind !== 'link' && part.text.trim() !== '' && <Excerpt part={part} />}
    </div>
  );
}

/** The parts of one input, in the order they were given. */
function byLabel(parts: GivenPart[]): [string, GivenPart[]][] {
  const groups = new Map<string, GivenPart[]>();
  for (const part of parts) groups.set(part.label, [...(groups.get(part.label) ?? []), part]);
  return [...groups.entries()];
}

interface RunGivenProps {
  /** `givenParts(run)`: TeamWork reads them once to know whether there is anything to list. */
  parts: GivenPart[];
  /** The report's heading level; each named input's own heading sits two below it. */
  level: 2 | 3;
}

/**
 * "What your team was given", in full: each part with its kind, size and notes, and the
 * start of its text. A run with several named inputs lists them under their labels.
 */
export function RunGiven({ parts, level }: RunGivenProps) {
  const groups = byLabel(parts);
  const labelLevel = (level + 2) as HeadingLevel;
  return (
    <div className="space-y-4">
      {groups.map(([label, items]) => (
        <div key={label}>
          {groups.length > 1 && (
            <Heading level={labelLevel} className="pt-2 text-sm font-semibold text-slate-200">
              {label}
            </Heading>
          )}
          <dl className="divide-y divide-white/[0.06]">
            {items.map((part, index) => (
              <GivenItem key={`${part.kind}-${part.name}-${index}`} part={part} />
            ))}
          </dl>
        </div>
      ))}
    </div>
  );
}
