import type { StepResult } from '../../core/api/types';
import { CountUp } from '../../core/ui/reactbits/CountUp';

interface RunStatsProps {
  results: StepResult[];
  outputCount: number;
  elapsedMs: number | null;
}

/** A finished run's totals: outputs, steps, stages and time, counting up on screen. */
export function RunStats({ results, outputCount, elapsedMs }: RunStatsProps) {
  const stageCount = new Set(results.map((result) => result.stage)).size;
  const stats = [
    { value: outputCount, label: outputCount === 1 ? 'output' : 'outputs', decimals: 0 },
    { value: results.length, label: 'steps', decimals: 0 },
    { value: stageCount, label: 'stages', decimals: 0 },
  ];
  if (elapsedMs !== null) stats.push({ value: elapsedMs / 1000, label: 's', decimals: 1 });
  const summary = stats
    .map((stat) => `${stat.value.toFixed(stat.decimals)} ${stat.label}`)
    .join(' · ');

  // The counting chips are visual; assistive tech reads the one-line summary.
  return (
    <div className="text-xs text-slate-400">
      <p className="sr-only">{summary}</p>
      <div aria-hidden="true" className="flex flex-wrap gap-2">
        {stats.map((stat) => (
          <span
            key={stat.label}
            className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1"
          >
            <CountUp
              to={stat.value}
              decimals={stat.decimals}
              className="font-semibold text-slate-100"
            />{' '}
            {stat.label}
          </span>
        ))}
      </div>
    </div>
  );
}
