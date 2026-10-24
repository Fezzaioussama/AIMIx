import { motion } from 'motion/react';
import { useRef } from 'react';
import type { KeyboardEvent } from 'react';

import { HERO_STEPS } from './content/product';
import { PerspectiveWindow } from './PerspectiveWindow';
import { PREVIEW_PANELS } from './previewPanels';
import { StackedSwap } from './StackedSwap';
import { STEP_INTERVAL_MS, useStepCarousel } from './useStepCarousel';

const TAB =
  'relative cursor-pointer overflow-hidden rounded-xl px-4 py-3 text-sm font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 sm:px-5';
const tabId = (id: string) => `hero-tab-${id}`;
const panelId = (id: string) => `hero-panel-${id}`;

/** The tab that an arrow key / Home / End moves to, or null for any other key. */
function targetIndex(key: string, current: number, count: number): number | null {
  if (key === 'ArrowRight') return (current + 1) % count;
  if (key === 'ArrowLeft') return (current - 1 + count) % count;
  if (key === 'Home') return 0;
  if (key === 'End') return count - 1;
  return null;
}

/**
 * The four steps of an AIMIx workflow as tabs over a product window (APG tabs
 * pattern: arrow keys move, Tab leaves). Advances itself until the visitor takes over.
 */
export function HeroSteps() {
  const { active, select, auto, hold } = useStepCarousel(HERO_STEPS.length);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);

  function handleKeyDown(event: KeyboardEvent) {
    const next = targetIndex(event.key, active, HERO_STEPS.length);
    if (next === null) return;
    event.preventDefault();
    select(next);
    tabs.current[next]?.focus();
  }

  return (
    <div
      onPointerEnter={() => hold(true)}
      onPointerLeave={() => hold(false)}
      onFocus={() => hold(true)}
      onBlur={() => hold(false)}
    >
      <div
        role="tablist"
        aria-label="The four steps of an AIMIx workflow"
        onKeyDown={handleKeyDown}
        className="mx-auto flex max-w-3xl flex-wrap justify-center gap-2"
      >
        {HERO_STEPS.map((item, index) => {
          const selected = index === active;
          return (
            <button
              key={item.id}
              ref={(node) => {
                tabs.current[index] = node;
              }}
              type="button"
              role="tab"
              id={tabId(item.id)}
              aria-selected={selected}
              aria-controls={panelId(item.id)}
              tabIndex={selected ? 0 : -1}
              onClick={() => select(index)}
              className={`${TAB} ${
                selected
                  ? 'bg-white/[0.08] text-white'
                  : 'text-slate-400 hover:bg-white/[0.04] hover:text-slate-100'
              }`}
            >
              <span aria-hidden="true" className="mr-2 text-slate-400 tabular-nums">
                0{index + 1}
              </span>
              {item.label}
              {selected && (
                <motion.span
                  key={`${index}-${auto}`}
                  aria-hidden="true"
                  initial={{ scaleX: auto ? 0 : 1 }}
                  animate={{ scaleX: 1 }}
                  transition={{ duration: auto ? STEP_INTERVAL_MS / 1000 : 0, ease: 'linear' }}
                  className="absolute inset-x-0 bottom-0 h-0.5 origin-left bg-gradient-to-r from-sky-400 via-indigo-500 to-purple-500"
                />
              )}
            </button>
          );
        })}
      </div>
      <StackedSwap
        activeIndex={active}
        className="mx-auto mt-5 max-w-xl text-center text-slate-400"
      >
        {HERO_STEPS.map((item) => (
          <p key={item.id}>{item.detail}</p>
        ))}
      </StackedSwap>
      <div className="mt-10">
        <PerspectiveWindow title="AIMIx · Example workflow">
          <StackedSwap activeIndex={active}>
            {HERO_STEPS.map((item) => {
              const Panel = PREVIEW_PANELS[item.id];
              return (
                <div
                  key={item.id}
                  role="tabpanel"
                  id={panelId(item.id)}
                  aria-labelledby={tabId(item.id)}
                >
                  <Panel />
                </div>
              );
            })}
          </StackedSwap>
        </PerspectiveWindow>
      </div>
    </div>
  );
}
