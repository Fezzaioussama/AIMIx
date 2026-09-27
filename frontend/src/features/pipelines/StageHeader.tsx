interface StageHeaderProps {
  stage: number;
  stepCount: number;
}

/** Labels a stage and says whether its steps run in parallel. */
export function StageHeader({ stage, stepCount }: StageHeaderProps) {
  return (
    <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
      <span>Stage {stage}</span>
      {stepCount > 1 && (
        <span className="rounded-md bg-indigo-400/15 px-2 py-0.5 normal-case tracking-normal text-indigo-300">
          {stepCount} steps in parallel
        </span>
      )}
    </div>
  );
}
