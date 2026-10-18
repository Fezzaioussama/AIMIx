import { useEffect, useLayoutEffect, useRef } from 'react';

import { BRAND_COLORS } from '../brand';
import { AuroraRenderer } from './aurora/renderer';
import type { AuroraSettings } from './aurora/renderer';
import { MAX_LAYERS, MAX_STOPS } from './aurora/shader';

export interface AuroraProps {
  colorStops?: readonly string[];
  amplitude?: number;
  blend?: number;
  speed?: number;
  height?: number;
  glow?: number;
  brightness?: number;
  layers?: number;
  opacity?: number;
  mouseInteraction?: boolean;
  intro?: boolean;
  /** Pixel-ratio cap. Below 1 renders a softer, cheaper aurora. */
  dpr?: number;
  className?: string;
}

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

/** Fills defaults and clamps each prop to the range the shader expects. */
function resolveSettings(props: AuroraProps): AuroraSettings {
  const stops = (props.colorStops ?? BRAND_COLORS).slice(0, MAX_STOPS);
  const first = stops[0] ?? '#ffffff';
  return {
    stops: stops.length >= 2 ? stops : [first, first],
    amplitude: Math.max(0, props.amplitude ?? 1),
    blend: clamp(props.blend ?? 0.5, 0, 1),
    speed: props.speed ?? 1,
    height: clamp(props.height ?? 0.45, 0, 1),
    glow: Math.max(0, props.glow ?? 0.6),
    brightness: Math.max(0, props.brightness ?? 1),
    layers: clamp(Math.round(props.layers ?? 1), 1, MAX_LAYERS),
    opacity: clamp(props.opacity ?? 1, 0, 1),
    mouseInteraction: props.mouseInteraction ?? true,
    intro: props.intro ?? true,
    dpr: props.dpr ?? window.devicePixelRatio ?? 1,
  };
}

/**
 * Animated aurora curtains, adapted from React Bits "Aurora" (reactbits.dev, see
 * LICENSE.md). Decorative only: where WebGL2 is unavailable it renders an empty layer.
 */
export function Aurora({ className = '', ...props }: AuroraProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<AuroraRenderer | null>(null);
  const settings = resolveSettings(props);
  const settingsRef = useRef(settings);

  // Hand the latest props to the running loop without restarting WebGL.
  useLayoutEffect(() => {
    settingsRef.current = settings;
    rendererRef.current?.wake();
  });

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;
    const renderer = AuroraRenderer.start(container, () => settingsRef.current);
    rendererRef.current = renderer;
    return () => {
      renderer?.dispose();
      rendererRef.current = null;
    };
  }, []);

  return (
    <div
      ref={containerRef}
      aria-hidden="true"
      className={`pointer-events-none absolute overflow-hidden ${className}`}
    />
  );
}
