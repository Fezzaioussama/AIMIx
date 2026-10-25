import { useRef, type KeyboardEvent } from 'react';

import type { RunStatus } from '../../core/api/types';
import { ActivePill } from '../../core/ui/ActivePill';
import { RUN_STATUS_STYLES } from '../runs/RunStatusBadge';
import { PANE_LABELS, PANE_ORDER, paneIds, type PaneId } from './missionPanes';

/** Where each key moves the selection: arrows wrap around, Home and End jump. */
const KEY_MOVES: Partial<Record<string, (index: number, count: number) => number>> = {
  ArrowRight: (index, count) => (index + 1) % count,
  ArrowLeft: (index, count) => (index - 1 + count) % count,
  Home: () => 0,
  End: (_index, count) => count - 1,
};

interface MissionTabsProps {
  active: PaneId;
  onChange: (pane: PaneId) => void;
  /** The newest run's status, shown on the Results tab. */
  runStatus: RunStatus | null;
}

/** The status of the newest run, small enough for the Results tab. */
function TabRunStatus({ status }: { status: RunStatus }) {
  const style = RUN_STATUS_STYLES[status];
  return (
    <span className="flex items-center gap-1 text-[11px] font-normal text-slate-300">
      <span aria-hidden="true" className={`size-1.5 rounded-full ${style.dot}`} />
      <span className="sr-only">, run </span>
      {style.label}
    </span>
  );
}

/**
 * The panes as tabs on a narrow screen (ARIA tabs: arrow keys move between them, Home
 * and End jump). The Results tab carries the newest run's status, so it stays in view.
 */
export function MissionTabs({ active, onChange, runStatus }: MissionTabsProps) {
  const tabs = useRef<Partial<Record<PaneId, HTMLButtonElement | null>>>({});

  function move(event: KeyboardEvent, index: number) {
    const next = KEY_MOVES[event.key]?.(index, PANE_ORDER.length);
    if (next === undefined) return;
    event.preventDefault();
    const pane = PANE_ORDER[next];
    onChange(pane);
    tabs.current[pane]?.focus();
  }

  return (
    <div
      role="tablist"
      aria-label="Mission"
      className="flex shrink-0 gap-1 border-b border-white/[0.06] bg-slate-950/60 p-2"
    >
      {PANE_ORDER.map((pane, index) => {
        const selected = pane === active;
        const ids = paneIds(pane);
        return (
          <button
            key={pane}
            ref={(node) => {
              tabs.current[pane] = node;
            }}
            type="button"
            role="tab"
            id={ids.tab}
            aria-controls={ids.panel}
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(pane)}
            onKeyDown={(event) => move(event, index)}
            className={`relative isolate flex min-w-0 flex-1 flex-col items-center justify-center rounded-lg px-2 py-1.5 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 ${
              selected ? 'text-white' : 'text-slate-300 hover:text-white'
            }`}
          >
            {selected && (
              <ActivePill
                layoutId="mission-tabs"
                className="bg-white/[0.08] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)]"
              />
            )}
            {PANE_LABELS[pane]}
            {pane === 'results' && runStatus !== null && <TabRunStatus status={runStatus} />}
          </button>
        );
      })}
    </div>
  );
}
