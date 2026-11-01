import { Fragment, useMemo, type ReactNode } from 'react';

import type { Run } from '../../../core/api/types';
import { countWords, plainTextOf } from '../../../core/markdown/documentText';
import { RenderedMarkdown } from '../../../core/markdown/RenderedMarkdown';
import { renderMarkdown } from '../../../core/markdown/renderMarkdown';
import { CostText } from '../../../core/ui/CostText';
import { FOCUS_RING } from '../../../core/ui/focus';
import { Heading } from '../../../core/ui/Heading';
import { countOf, describeCost, usageOfStep } from '../../../core/usageFormat';
import { modelLabel } from '../../pipelines/modelLabel';
import { CHECK_TONE } from './checkTone';
import { DeliverableActions } from './DeliverableActions';
import type { DeliverableParts } from './deliverableFiles';
import { reportIds, type DeliverableView } from './reportModel';
import type { BylineCheck } from './signOffCopy';

/** Under this many words a byline counts characters too: a post's length limit is in them. */
const SHORT_WORDS = 300;

/** A deliverable as it reads, copies and downloads, and how long it is. */
interface Reading extends DeliverableParts {
  words: number;
  characters: number;
}

function readingOf(title: string, markdown: string): Reading {
  const html = renderMarkdown(markdown);
  const text = plainTextOf(html);
  return { title, markdown, html, text, words: countWords(text), characters: text.length };
}

/** "by Writer · llama-4": who wrote it, then on which model. */
function makerFacts(role: string, model: string): string[] {
  return [role && `by ${role}`, modelLabel(model)].filter(Boolean);
}

/** "210 words · 1,342 characters": how long it is (characters only when it is short). */
function lengthFacts(reading: Reading): string[] {
  if (reading.words === 0) return [];
  const facts = [countOf(reading.words, 'word')];
  if (reading.words < SHORT_WORDS) facts.push(countOf(reading.characters, 'character'));
  return facts;
}

function CheckWords({ check }: { check: BylineCheck }) {
  const tone = CHECK_TONE[check.tone];
  return (
    <span className={`inline-flex items-baseline gap-1 ${tone.text}`}>
      <tone.Icon aria-hidden="true" className={`size-3.5 shrink-0 self-center ${tone.icon}`} />
      {check.words}
    </span>
  );
}

/** One quiet line of facts, " · " between them. */
function Byline({ parts }: { parts: ReactNode[] }) {
  return (
    <p className="mt-2 text-sm text-pretty text-slate-400">
      {parts.map((part, index) => (
        <Fragment key={index}>
          {index > 0 && ' · '}
          {part}
        </Fragment>
      ))}
    </p>
  );
}

/** "by Writer · llama-4 · $0.0012 · 210 words · Approved by the Orchestrator". */
function bylineParts(view: DeliverableView, reading: Reading, check: BylineCheck | null) {
  const cost = describeCost(usageOfStep(view.step));
  const parts: ReactNode[] = makerFacts(view.role, view.step.model);
  if (cost) parts.push(<CostText view={cost} compact />);
  parts.push(...lengthFacts(reading));
  if (check) parts.push(<CheckWords check={check} />);
  return parts;
}

interface DeliverableDocProps {
  run: Run;
  view: DeliverableView;
  /** The check its byline carries (`bylineCheck`); null when nothing checks it. */
  check: BylineCheck | null;
  /** The report's heading level: the title's, and where the text's own headings start under. */
  level: 2 | 3;
}

/**
 * A ready deliverable as a document to read: its title row stays in view while it scrolls
 * (with Copy and Download), then who wrote it, on which model and at what cost, and
 * whether it was checked, then the text.
 */
export function DeliverableDoc({ run, view, check, level }: DeliverableDocProps) {
  const { output } = view.step;
  const reading = useMemo(() => readingOf(view.title, output), [view.title, output]);
  const ids = reportIds(run.id);
  const order = view.step.step_order;
  const empty = output.trim() === '';
  return (
    <article
      id={ids.deliverable(order)}
      aria-labelledby={ids.title(order)}
      className="scroll-mt-[calc(var(--sticky-top,0px)+1rem)]"
    >
      {/* A title too long to sit beside the buttons takes its own line, the buttons the next:
          never a narrow column of one word per line under a phone's top bar. The frosted
          ground is a layer behind the row, not the row itself: a backdrop-filter on the row
          would keep the Download menu, which hangs below it, from painting its background.
          Where the browser can tell (a scroll-state container), the ground shows only while
          the row is stuck, so no darker band sits on the page's glow; elsewhere it stays. On
          a phone it reaches into the 16px gutters, where the glow would frame it. */}
      <div className="sticky top-[var(--sticky-top,0px)] z-10 flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-white/[0.06] py-2 [container-type:scroll-state] before:absolute before:inset-0 before:-z-10 max-sm:before:-inset-x-4 before:bg-ground/90 before:backdrop-blur-md before:transition-opacity before:duration-150 before:ease-out [@container_not_scroll-state(stuck:top)]:before:opacity-0">
        <Heading
          level={level}
          id={ids.title(order)}
          tabIndex={-1}
          className={`min-w-0 flex-auto rounded-sm text-lg font-semibold text-balance text-white ${FOCUS_RING}`}
        >
          {view.title}
        </Heading>
        {!empty && <DeliverableActions parts={reading} />}
      </div>
      <Byline parts={bylineParts(view, reading, check)} />
      {empty ? (
        <p className="mt-5 text-sm text-slate-400">This agent finished without writing anything.</p>
      ) : (
        <RenderedMarkdown
          markdown={output}
          headingBase={level + 1}
          className="mt-5 text-slate-200"
        />
      )}
    </article>
  );
}
