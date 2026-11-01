import { FileText, Globe, X } from 'lucide-react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { useLayoutEffect, useRef, type Ref } from 'react';

import { Spinner } from '../../core/ui/Spinner';
import { documentDetails } from '../pipelines/pipelineInputs';
import { sourceLabel } from '../pipelines/webLinks';
import { PlacementChoices, placementText } from './DocumentPlacementNotice';
import type { DocumentPlacement, PendingDocument } from './missionDocuments';
import type { MissionDocuments } from './useMissionDocuments';

const EASE = [0.22, 1, 0.36, 1] as const;

/** A chip comes in soft (fade, slight scale, blur) and leaves faster than it came. */
const CHIP_MOTION = {
  initial: { opacity: 0, scale: 0.96, filter: 'blur(2px)' },
  animate: { opacity: 1, scale: 1, filter: 'blur(0px)', transition: { duration: 0.2, ease: EASE } },
  exit: {
    opacity: 0,
    scale: 0.96,
    filter: 'blur(2px)',
    transition: { duration: 0.15, ease: EASE },
  },
};

/** Under reduced motion a chip only fades, and quickly: no scale, no blur. */
const CHIP_FADE = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: { duration: 0.15, ease: EASE } },
  exit: { opacity: 0, transition: { duration: 0.15, ease: EASE } },
};

/**
 * The chips stop growing at an eighth of the screen's height and scroll, so on a short
 * screen the conversation above keeps most of it; the cap usually cuts a chip in two,
 * which shows there is more. A chip that gets keyboard focus scrolls into view, as any
 * focused control does.
 */
const CHIPS_AREA = 'max-h-[max(4.5rem,12dvh)] overflow-y-auto overscroll-y-contain scroll-py-1';

/**
 * How a chip fits its name: a link's label is already cut in the middle (`sourceLabel`),
 * so it shows whole, breaking anywhere if it must; a file's own name is cut at its end.
 * Either way the title holds it whole.
 */
const NAME_FIT: Record<PendingDocument['kind'], string> = {
  link: 'wrap-anywhere',
  file: 'max-w-56 truncate',
};

/** The remove button is small, but its target reaches 44px on a phone. */
const REMOVE =
  'relative grid size-6 shrink-0 place-items-center rounded-md text-slate-300 transition-colors before:absolute before:-inset-2.5 hover:bg-white/10 hover:text-white focus-visible:outline-2 focus-visible:outline-sky-400 sm:before:-inset-1';

interface ComposerAttachmentsProps {
  documents: MissionDocuments;
  /** There is a team: the documents wait for its run. */
  hasTeam: boolean;
  /** Read documents a run form open now did not take, and why. */
  placement: DocumentPlacement | null;
  /** Where focus goes once the last chip is removed: the text box. */
  onEmptied: () => void;
}

/**
 * Where focus goes when a chip leaves: to the next chip that stays, else the one before
 * it, else the text box (`onEmptied`). Removing one moves focus first (`leave`); a chip
 * can also leave on its own (its document went into the run form), and if its button had
 * focus, focus moves the same way before the chip's exit takes the button away.
 */
function useChipFocus(items: PendingDocument[], onEmptied: () => void) {
  const buttons = useRef(new Map<string, HTMLButtonElement>());
  const shown = useRef(items);

  function focusPast(list: PendingDocument[], index: number, stays: (id: string) => boolean) {
    const next =
      list.slice(index + 1).find((item) => stays(item.id)) ??
      list
        .slice(0, index)
        .reverse()
        .find((item) => stays(item.id));
    const button = next && buttons.current.get(next.id);
    if (button) button.focus();
    else onEmptied();
  }

  useLayoutEffect(() => {
    const before = shown.current;
    shown.current = items;
    const stays = (id: string) => items.some((item) => item.id === id);
    const index = before.findIndex(
      (item) => !stays(item.id) && buttons.current.get(item.id) === document.activeElement,
    );
    if (index >= 0) focusPast(before, index, stays);
  });

  return {
    buttonRef: (id: string) => (node: HTMLButtonElement | null) => {
      if (node) buttons.current.set(id, node);
      else buttons.current.delete(id);
    },
    leave: (index: number) => focusPast(items, index, (id) => id !== items[index].id),
  };
}

/**
 * The documents added to the mission, as chips above the text: each says it is being
 * read, then its size, or why the server could not read it; each can be removed. What
 * happens to them is announced politely; a failure is an alert. While a run form is open,
 * it says why the ones still here are not in it (and asks where they go when it can).
 */
export function ComposerAttachments(props: ComposerAttachmentsProps) {
  const { documents, hasTeam, placement, onEmptied } = props;
  const { items, notice, status } = documents;
  const focus = useChipFocus(items, onEmptied);

  function remove(index: number) {
    focus.leave(index);
    documents.remove(items[index].id);
  }

  return (
    <div className="relative">
      <ul
        aria-label="Attached documents"
        className={`flex flex-wrap gap-1.5 px-1 pt-1 empty:p-0 ${CHIPS_AREA}`}
      >
        <AnimatePresence initial={false}>
          {items.map((item, index) => (
            <Chip
              key={item.id}
              item={item}
              onRemove={() => remove(index)}
              buttonRef={focus.buttonRef(item.id)}
            />
          ))}
        </AnimatePresence>
      </ul>
      {hasTeam && items.length > 0 && placement === null && (
        <p className="mt-1.5 px-1 text-xs text-slate-400">Your team gets these when it runs.</p>
      )}
      <p aria-live="polite" className="mt-1.5 px-1 text-xs text-amber-200 empty:mt-0">
        {[placement && placementText(placement), notice].filter(Boolean).join(' ')}
      </p>
      {placement && <PlacementChoices placement={placement} onPlaced={onEmptied} />}
      <p role="status" className="sr-only">
        {status}
      </p>
    </div>
  );
}

interface ChipProps {
  item: PendingDocument;
  onRemove: () => void;
  buttonRef: Ref<HTMLButtonElement>;
}

/**
 * One document: its icon, its name and details (wrapping in their own column), and ×,
 * which stays at the top right however the text wraps. The icon and × line up with the
 * first line of text.
 */
function Chip({ item, onRemove, buttonRef }: ChipProps) {
  const name = sourceLabel(item.state === 'read' ? item.document.filename : item.source);
  const Icon = item.kind === 'link' ? Globe : FileText;
  const failed = item.state === 'failed';
  const reduced = useReducedMotion();
  return (
    <motion.li
      {...(reduced ? CHIP_FADE : CHIP_MOTION)}
      className={`grid max-w-full min-w-0 grid-cols-[auto_minmax(0,1fr)_auto] items-start gap-x-2 rounded-lg border py-1 pr-1 pl-2 text-xs ${failed ? 'basis-full border-amber-300/25 bg-amber-300/[0.06]' : 'border-white/10 bg-white/[0.05]'}`}
    >
      <span className="flex h-6 items-center">
        <Icon
          aria-hidden="true"
          className={`size-3.5 ${failed ? 'text-amber-300' : 'text-sky-300'}`}
        />
      </span>
      <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 py-1">
        <span
          title={item.source}
          className={`min-w-0 font-medium text-slate-100 ${NAME_FIT[item.kind]}`}
        >
          {name}
        </span>
        <ChipDetails item={item} />
      </span>
      <button
        ref={buttonRef}
        type="button"
        aria-label={`Remove ${name}`}
        onClick={onRemove}
        className={REMOVE}
      >
        <X aria-hidden="true" className="size-3.5" />
      </button>
      {item.state === 'failed' && (
        <span role="alert" className="col-span-2 col-start-2 pb-0.5 text-amber-300">
          {item.error}
        </span>
      )}
    </motion.li>
  );
}

function ChipDetails({ item }: { item: PendingDocument }) {
  if (item.state === 'reading') {
    return (
      <span className="flex shrink-0 items-center gap-1.5 text-slate-300">
        <Spinner decorative className="size-3" />
        Reading…
      </span>
    );
  }
  if (item.state === 'read') {
    return <span className="text-slate-400">{documentDetails(item.document)}</span>;
  }
  return null;
}
