import { Children } from 'react';
import type { ReactNode } from 'react';

interface StackedSwapProps {
  /** Which child is showing. */
  activeIndex: number;
  /** One child per state. */
  children: ReactNode;
  className?: string;
}

/**
 * Cross-fades between states that all stay mounted in one grid cell. The cell is as
 * tall as the tallest state, so switching never moves the content below it — unlike
 * swapping children, whose heights differ (a layout shift, worst on a phone).
 * Hidden states are `inert` and `aria-hidden`: unfocusable and unannounced.
 */
export function StackedSwap({ activeIndex, children, className = '' }: StackedSwapProps) {
  return (
    // grid-cols-1 is minmax(0, 1fr): without it the one column grows to the widest
    // state's min-content (e.g. a long unbroken line) and overflows its container.
    <div className={`grid grid-cols-1 ${className}`}>
      {Children.map(children, (child, index) => {
        const active = index === activeIndex;
        return (
          <div
            inert={!active}
            aria-hidden={!active}
            className={`col-start-1 row-start-1 transition-[opacity,translate] duration-300 ease-out motion-reduce:transition-none ${
              active ? 'translate-y-0 opacity-100' : 'pointer-events-none translate-y-2 opacity-0'
            }`}
          >
            {child}
          </div>
        );
      })}
    </div>
  );
}
