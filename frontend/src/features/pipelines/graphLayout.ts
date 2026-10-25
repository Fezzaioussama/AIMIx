/**
 * How wide each part of the stage diagram is. The loop-back lines are drawn in a row of
 * their own above the stages and must line up with them, so the diagram and the lines both
 * read their widths from here.
 */
export const TERMINAL_WIDTH = 'w-36';
export const CONNECTOR_WIDTH = 'w-10';

/**
 * A stage's column: the width of its nodes, plus the room of the fork and merge brackets
 * when its steps run in parallel.
 */
export function columnWidth(parallel: boolean): string {
  return parallel ? 'w-[15.5rem]' : 'w-56';
}
