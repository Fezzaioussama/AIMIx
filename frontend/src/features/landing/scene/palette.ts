import { Color } from 'three';

import { BRAND_COLORS } from '../../../core/ui/brand';

const STOPS = BRAND_COLORS.map((hex) => new Color(hex));
const WHITE = new Color('#ffffff');

/** The colour `t` (0..1) of the way along the logo's sky → indigo → purple gradient. */
export function brandColorAt(t: number): Color {
  const scaled = Math.min(Math.max(t, 0), 1) * (STOPS.length - 1);
  const index = Math.min(Math.floor(scaled), STOPS.length - 2);
  return STOPS[index].clone().lerp(STOPS[index + 1], scaled - index);
}

/** A node's bright centre: its stage colour pushed toward white. */
export const coreColor = (color: Color): Color => color.clone().lerp(WHITE, 0.6);
