export interface StageGroup<T> {
  stage: number;
  items: T[];
}

/**
 * Group items into execution stages, ascending. Items keep their relative order
 * within a stage. Shared by the step editors and the run results so both show
 * the same grouping the backend executes.
 */
export function groupByStage<T>(items: T[], stageOf: (item: T) => number): StageGroup<T>[] {
  const groups = new Map<number, T[]>();
  for (const item of items) {
    const stage = stageOf(item);
    groups.set(stage, [...(groups.get(stage) ?? []), item]);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a - b)
    .map(([stage, grouped]) => ({ stage, items: grouped }));
}

/** The stage a newly added step gets: after every existing one, i.e. sequential. */
export function nextStage(steps: { stage: number }[]): number {
  return steps.reduce((highest, step) => Math.max(highest, step.stage), 0) + 1;
}
