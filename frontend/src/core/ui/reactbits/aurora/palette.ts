import { MAX_STOPS } from './shader';

type Rgb = [number, number, number];

const WHITE: Rgb = [1, 1, 1];

let probe: CanvasRenderingContext2D | null | undefined;

/** Any CSS colour → sRGB channels in 0..1, resolved by painting a 1×1 2D canvas. */
function parseColor(value: string): Rgb {
  probe ??= document.createElement('canvas').getContext('2d', { willReadFrequently: true });
  if (!probe) return WHITE;
  probe.clearRect(0, 0, 1, 1);
  probe.fillStyle = '#ffffff';
  probe.fillStyle = value;
  probe.fillRect(0, 0, 1, 1);
  const [r, g, b] = probe.getImageData(0, 0, 1, 1).data;
  return [r / 255, g / 255, b / 255];
}

/** sRGB → OKLCH (lightness, chroma, hue), the space the shader blends stops in. */
function toOklch(rgb: Rgb): Rgb {
  const [r, g, b] = rgb.map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  const lab = [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
  return [lab[0], Math.hypot(lab[1], lab[2]), Math.atan2(lab[2], lab[1])];
}

/** Keep each hue within π of the previous one so the ramp takes the short way round. */
function unwrapHues(stops: Rgb[]): Rgb[] {
  const known = stops.findIndex((stop) => stop[1] > 0.02);
  let previous = known === -1 ? 0 : stops[known][2];
  return stops.map(([lightness, chroma, raw]) => {
    let hue = chroma > 0.02 ? raw : previous;
    while (hue - previous > Math.PI) hue -= Math.PI * 2;
    while (hue - previous < -Math.PI) hue += Math.PI * 2;
    previous = hue;
    return [lightness, chroma, hue];
  });
}

/** The `uStops` uniform: up to MAX_STOPS colours as packed OKLCH triples. */
export function buildPalette(stops: readonly string[]): Float32Array {
  const palette = new Float32Array(MAX_STOPS * 3);
  unwrapHues(stops.map((stop) => toOklch(parseColor(stop)))).forEach((stop, index) =>
    palette.set(stop, index * 3),
  );
  return palette;
}
