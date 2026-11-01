import { Check, Copy, Download } from 'lucide-react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from 'react';

import { useCopyToClipboard, type CopyStatus } from '../../../core/hooks/useCopyToClipboard';
import { saveBlob } from '../../../core/saveBlob';
import { FOCUS_RING, TOUCH } from '../../../core/ui/focus';
import { BLUR, DURATION, EASE_SMOOTH_OUT, ICON_SPRING } from '../../../core/ui/motionTokens';
import { RUN_BUTTON } from '../runButtons';
import {
  DOWNLOAD_FORMATS,
  safeFileName,
  type DeliverableParts,
  type DownloadFormat,
} from './deliverableFiles';

/** M8: the copied check scales in from a quarter of its size, out of a 4px blur. */
const ICON_SWAP = {
  initial: { opacity: 0, scale: 0.25, filter: BLUR.icon },
  animate: { opacity: 1, scale: 1, filter: BLUR.none },
  exit: { opacity: 0, scale: 0.25, filter: BLUR.icon },
  transition: ICON_SPRING,
} as const;

/** M9: the menu grows from Download's corner, and leaves faster than it came. */
const MENU_MOTION = {
  initial: { opacity: 0, scale: 0.97 },
  animate: { opacity: 1, scale: 1, transition: { duration: DURATION.fast, ease: EASE_SMOOTH_OUT } },
  exit: {
    opacity: 0,
    scale: 0.99,
    transition: { duration: DURATION.quick, ease: EASE_SMOOTH_OUT },
  },
} as const;

/** Reduced motion keeps only a 150ms fade, for the icon and the menu alike. */
const FADING = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
  transition: { duration: DURATION.quick },
} as const;

/** What the copy status says: the screen reader hears a copy; everyone sees a failure. */
const COPY_WORDS: Record<CopyStatus, (title: string) => string> = {
  idle: () => '',
  copied: (title) => `${title} copied.`,
  failed: () => 'Could not copy. Select the text and copy it yourself.',
};

const FORMATS = Object.keys(DOWNLOAD_FORMATS) as DownloadFormat[];

/** One of two labels sharing a grid cell, so the button keeps its width as they swap. */
function SwapLabel({ shown, children }: { shown: boolean; children: ReactNode }) {
  return (
    <span
      className={`col-start-1 row-start-1 transition-[opacity,filter] duration-150 ease-in-out motion-reduce:filter-none ${shown ? 'opacity-100' : 'opacity-0 blur-[2px]'}`}
    >
      {children}
    </span>
  );
}

interface CopyButtonProps {
  title: string;
  copied: boolean;
  onCopy: () => void;
}

function CopyButton({ title, copied, onCopy }: CopyButtonProps) {
  const swap = useReducedMotion() ? FADING : ICON_SWAP;
  const Icon = copied ? Check : Copy;
  return (
    <button
      type="button"
      onClick={onCopy}
      aria-label={`Copy ${title} as formatted text`}
      data-copied={copied}
      className={`${RUN_BUTTON.neutral} cursor-pointer`}
    >
      <span aria-hidden="true" className="relative grid size-4 place-items-center">
        <AnimatePresence mode="popLayout" initial={false}>
          <motion.span
            key={copied ? 'check' : 'copy'}
            className="grid place-items-center"
            {...swap}
          >
            <Icon className="size-4" />
          </motion.span>
        </AnimatePresence>
      </span>
      <span aria-hidden="true" className="grid">
        <SwapLabel shown={!copied}>Copy</SwapLabel>
        <SwapLabel shown={copied}>Copied</SwapLabel>
      </span>
    </button>
  );
}

interface FormatMenuProps {
  id: string;
  title: string;
  onChoose: (format: DownloadFormat) => void;
}

/** The formats to download, anchored under Download's right edge. */
function FormatMenu({ id, title, onChoose }: FormatMenuProps) {
  const look = useReducedMotion() ? FADING : MENU_MOTION;
  return (
    <motion.div
      id={id}
      role="group"
      aria-label={`Download ${title} as`}
      style={{ transformOrigin: 'top right' }}
      className="absolute top-full right-0 z-20 mt-2 w-64 rounded-xl border border-white/10 bg-ground/95 p-1 shadow-[0_12px_32px_-12px_rgba(0,0,0,0.8)] backdrop-blur-md"
      {...look}
    >
      {FORMATS.map((format) => {
        const spec = DOWNLOAD_FORMATS[format];
        return (
          <button
            key={format}
            type="button"
            onClick={() => onChoose(format)}
            className={`flex w-full cursor-pointer flex-col items-start justify-center rounded-lg px-3 py-2 text-left text-sm text-slate-100 transition-colors duration-150 ease-out hover:bg-white/10 ${TOUCH} ${FOCUS_RING}`}
          >
            {spec.label}
            {spec.hint && <span className="text-xs text-slate-400">{spec.hint}</span>}
          </button>
        );
      })}
    </motion.div>
  );
}

/**
 * While the menu is open, a press outside `area` closes it, and the focus goes back to
 * `trigger` unless the press put it on another control.
 */
function useCloseOnPressOutside(
  open: boolean,
  area: RefObject<HTMLElement | null>,
  trigger: RefObject<HTMLElement | null>,
  onClose: () => void,
) {
  useEffect(() => {
    if (!open) return;
    function pressedOutside(event: PointerEvent) {
      if (area.current?.contains(event.target as Node)) return;
      onClose();
      // Once the press has moved the focus, and only if it moved it nowhere.
      window.setTimeout(() => {
        if (document.activeElement === document.body) trigger.current?.focus();
      });
    }
    document.addEventListener('pointerdown', pressedOutside);
    return () => document.removeEventListener('pointerdown', pressedOutside);
  }, [open, area, trigger, onClose]);
}

/**
 * Download, then a format. Escape, a choice or a press outside closes the menu and gives
 * the focus back to Download (a press on another control keeps it there).
 */
function DownloadMenu({ parts }: { parts: DeliverableParts }) {
  const [open, setOpen] = useState(false);
  const area = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menuId = useId();
  const dismiss = useCallback(() => setOpen(false), []);
  useCloseOnPressOutside(open, area, trigger, dismiss);

  function close() {
    setOpen(false);
    trigger.current?.focus();
  }

  function choose(format: DownloadFormat) {
    const spec = DOWNLOAD_FORMATS[format];
    const blob = new Blob([spec.body(parts)], { type: spec.mime });
    saveBlob(blob, `${safeFileName(parts.title)}.${spec.extension}`);
    close();
  }

  return (
    <div
      ref={area}
      className="relative"
      onKeyDown={(event) => {
        if (event.key === 'Escape' && open) close();
      }}
    >
      <button
        ref={trigger}
        type="button"
        aria-expanded={open}
        aria-controls={menuId}
        aria-label={`Download ${parts.title}`}
        onClick={() => setOpen((shown) => !shown)}
        className={`${RUN_BUTTON.neutral} cursor-pointer`}
      >
        <Download aria-hidden="true" className="size-4" />
        Download
      </button>
      <AnimatePresence initial={false}>
        {open && <FormatMenu id={menuId} title={parts.title} onChoose={choose} />}
      </AnimatePresence>
    </div>
  );
}

/**
 * A deliverable's Copy and Download, labelled at every width. Copy puts it on the
 * clipboard formatted for a rich editor and as plain text for a text field.
 */
export function DeliverableActions({ parts }: { parts: DeliverableParts }) {
  const { status, copyRich } = useCopyToClipboard();
  return (
    <div className="ml-auto grid shrink-0 justify-items-end gap-1">
      <div className="flex items-center gap-2">
        <CopyButton
          title={parts.title}
          copied={status === 'copied'}
          onCopy={() => void copyRich({ html: parts.html, text: parts.text })}
        />
        <DownloadMenu parts={parts} />
      </div>
      <p
        role="status"
        className={
          status === 'failed' ? 'w-0 min-w-full text-right text-xs text-amber-300' : 'sr-only'
        }
      >
        {COPY_WORDS[status](parts.title)}
      </p>
    </div>
  );
}
