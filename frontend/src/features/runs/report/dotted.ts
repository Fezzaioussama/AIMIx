/**
 * A row of facts or links that wraps, with a small dot in the gap before each one
 * ("Done · 4 min 54 s · $0.0708 of $1.00 limit"). The frame's left edge clips the dot of
 * whatever starts a line, so no line starts with a dot; it clips no focus ring.
 */
export const DOTTED = {
  /** Clips the dot of each line's first item, leaving 4px for a focus ring. */
  frame: '[clip-path:inset(-8px_-8px_-8px_-4px)]',
  /** Pulled left by one gap, so the first item sits on the frame's edge. */
  row: '-ml-5 flex flex-wrap items-center gap-y-1',
  /** One item, its dot centred in the 20px gap before it. */
  item: 'relative inline-flex items-center pl-5 before:absolute before:top-1/2 before:left-[8.5px] before:size-[3px] before:-translate-y-1/2 before:rounded-full before:bg-slate-500',
} as const;
