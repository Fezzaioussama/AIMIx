import { useRef, type KeyboardEvent, type Ref } from 'react';

import type { RunStatus } from '../../core/api/types';
import { ActivePill } from '../../core/ui/ActivePill';
import { FOCUS_RING } from '../../core/ui/focus';
import { RUN_STATUS_STYLES } from '../runs/RunStatusBadge';
import { PANE_LABELS, PANE_ORDER, paneIds, type PaneId } from './missionPanes';

/** Where each key moves the selection: arrows wrap around, Home and End jump. */
const KEY_MOVES: Partial<Record<string, (index: number, count: number) => number>> = {
  ArrowRight: (index, count) => (index + 1) % count,
  ArrowLeft: (index, count) => (index - 1 + count) % count,
  Home: () => 0,
  End: (_index, count) => count - 1,
};

/** The status of the newest run, small enough for the Results tab. */
function TabRunStatus({ status }: { status: RunStatus }) {
  const style = RUN_STATUS_STYLES[status];
  return (
    <span className="flex items-center gap-1 text-[11px] font-normal text-slate-300">
      <span aria-hidden="true" className={`size-1.5 rounded-full ${style.dot}`} />
      <span aria-hidden="true">{style.label}</span>
      <span className="sr-only">{`, run ${style.label.toLowerCase()}`}</span>
    </span>
  );
}

/**
 * The full bar of a narrow screen (equal tabs, the status under the name), or the compact
 * one over the main column of two (tabs as wide as their words, the status beside them).
 */
const LOOKS = {
  full: {
    list: 'bg-slate-950/60 p-2',
    tab: 'min-w-0 flex-1 flex-col justify-center px-2 py-1.5',
  },
  compact: {
    list: 'px-6 py-2',
    tab: 'h-10 flex-none flex-row gap-2 px-4 pointer-coarse:h-11',
  },
};

interface TabProps {
  pane: PaneId;
  /** The tab's own layout classes (`LOOKS`). */
  look: string;
  selected: boolean;
  /** The newest run's status, shown on the Results tab. */
  runStatus: RunStatus | null;
  buttonRef: Ref<HTMLButtonElement>;
  onSelect: () => void;
  onKeyDown: (event: KeyboardEvent) => void;
}

function Tab({ pane, look, selected, runStatus, buttonRef, onSelect, onKeyDown }: TabProps) {
  const ids = paneIds(pane);
  return (
    <button
      ref={buttonRef}
      type="button"
      role="tab"
      id={ids.tab}
      aria-controls={ids.panel}
      aria-selected={selected}
      tabIndex={selected ? 0 : -1}
      onClick={onSelect}
      onKeyDown={onKeyDown}
      className={`relative isolate flex items-center rounded-lg text-sm font-medium transition-colors ${look} ${FOCUS_RING} ${
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
}

interface MissionTabsProps {
  /** The panes offered, in order; all three by default. */
  panes?: readonly PaneId[];
  /** The compact bar over the main column of two (team and results). */
  compact?: boolean;
  active: PaneId;
  onChange: (pane: PaneId) => void;
  /** The newest run's status, shown on the Results tab. */
  runStatus: RunStatus | null;
}

/**
 * The panes as tabs (ARIA tabs: arrow keys move between them, Home and End jump): all
 * three on a narrow screen, or the team and the results over the main column of two.
 * The Results tab carries the newest run's status, so it stays in view.
 */
export function MissionTabs({
  panes = PANE_ORDER,
  compact = false,
  active,
  onChange,
  runStatus,
}: MissionTabsProps) {
  const tabs = useRef<Partial<Record<PaneId, HTMLButtonElement | null>>>({});
  const look = compact ? LOOKS.compact : LOOKS.full;

  function move(event: KeyboardEvent, index: number) {
    const next = KEY_MOVES[event.key]?.(index, panes.length);
    if (next === undefined) return;
    event.preventDefault();
    const pane = panes[next];
    onChange(pane);
    tabs.current[pane]?.focus();
  }

  return (
    <div
      role="tablist"
      aria-label="Mission"
      className={`flex shrink-0 gap-1 border-b border-white/[0.06] ${look.list}`}
    >
      {panes.map((pane, index) => (
        <Tab
          key={pane}
          pane={pane}
          look={look.tab}
          selected={pane === active}
          runStatus={runStatus}
          buttonRef={(node) => {
            tabs.current[pane] = node;
          }}
          onSelect={() => onChange(pane)}
          onKeyDown={(event) => move(event, index)}
        />
      ))}
    </div>
  );
}
