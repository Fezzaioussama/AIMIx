import { useReducedMotion } from 'motion/react';
import { useEffect, useRef } from 'react';
import type { MouseEvent, ReactNode } from 'react';

import { BRAND_HIGHLIGHT } from '../brand';
import { createSparkEngine } from './clickSparkEngine';
import type { SparkEngine, SparkOptions } from './clickSparkEngine';

interface ClickSparkProps extends Partial<SparkOptions> {
  children: ReactNode;
  className?: string;
}

const DEFAULTS: SparkOptions = {
  color: BRAND_HIGHLIGHT,
  count: 8,
  radius: 22,
  size: 10,
  duration: 420,
};

/**
 * Sparks burst from wherever its children are clicked — adapted from React Bits
 * "ClickSpark" (reactbits.dev, see LICENSE.md). The canvas overhangs the children
 * so sparks are not clipped; options are read once, on the first click.
 */
export function ClickSpark({ children, className = '', ...options }: ClickSparkProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const engineRef = useRef<SparkEngine | null>(null);
  const reduceMotion = useReducedMotion();

  useEffect(() => () => engineRef.current?.dispose(), []);

  function handleClick(event: MouseEvent<HTMLSpanElement>) {
    const canvas = canvasRef.current;
    if (reduceMotion || !canvas) return;
    engineRef.current ??= createSparkEngine(canvas, { ...DEFAULTS, ...options });
    // A keyboard "click" has no pointer position (detail 0): burst from the centre.
    const rect = event.currentTarget.getBoundingClientRect();
    const fromKeyboard = event.detail === 0;
    engineRef.current?.burst(
      fromKeyboard ? rect.left + rect.width / 2 : event.clientX,
      fromKeyboard ? rect.top + rect.height / 2 : event.clientY,
    );
  }

  return (
    <span className={`relative ${className}`} onClick={handleClick}>
      {children}
      <canvas
        ref={canvasRef}
        aria-hidden="true"
        className="pointer-events-none absolute -top-10 -left-10 h-[calc(100%+5rem)] w-[calc(100%+5rem)]"
      />
    </span>
  );
}
