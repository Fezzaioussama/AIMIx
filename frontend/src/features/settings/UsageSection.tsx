import type { ReactNode } from 'react';

import type { PipelineUsage, UsageReport } from '../../core/api/types';
import { CostText } from '../../core/ui/CostText';
import {
  describeCost,
  formatCount,
  formatCost,
  tokenBreakdown,
  totalTokens,
} from '../../core/usageFormat';
import { USAGE_DAYS, useUsage } from './useUsage';

/** Settings → Usage: what the account's runs used and cost lately. */
export function UsageSection() {
  const { report, error, loading } = useUsage(USAGE_DAYS);

  return (
    <section aria-labelledby="usage-heading" className="mt-12 border-t border-white/10 pt-10">
      <h2 id="usage-heading" className="text-2xl font-bold tracking-tight">
        Usage
      </h2>
      <p className="mt-2 mb-6 text-sm text-slate-400">
        What your runs used in the last {USAGE_DAYS} days, and what their model calls cost.
      </p>
      {loading && <p className="text-sm text-slate-400">Loading your usage…</p>}
      {error && (
        <p role="alert" className="text-sm text-red-400">
          {error}
        </p>
      )}
      {report && <UsageSummary report={report} />}
    </section>
  );
}

function UsageSummary({ report }: { report: UsageReport }) {
  if (report.runs === 0) {
    return <p className="text-sm text-slate-400">No runs in the last {report.days} days.</p>;
  }
  const cost = describeCost(report.usage);
  return (
    <>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Stat label="Runs">{formatCount(report.runs)}</Stat>
        <Stat label="Cost">
          {cost ? <CostText view={cost} compact /> : formatCost(report.usage.cost_usd ?? 0)}
        </Stat>
        <Stat label="Tokens" note={tokenBreakdown(report.usage)}>
          {formatCount(totalTokens(report.usage))}
        </Stat>
      </dl>
      {!report.usage.cost_complete && (
        <p className="mt-3 text-xs text-slate-400">
          Some runs used models whose cost is unknown, so the real cost is higher.
        </p>
      )}
      <h3 className="mt-8 mb-3 text-sm font-semibold text-slate-300">By pipeline</h3>
      <ul aria-label="Usage by pipeline" className="space-y-2">
        {report.pipelines.map((entry) => (
          <PipelineRow key={entry.pipeline_id ?? `deleted:${entry.pipeline_name}`} entry={entry} />
        ))}
      </ul>
    </>
  );
}

interface StatProps {
  label: string;
  note?: string;
  children: ReactNode;
}

function Stat({ label, note, children }: StatProps) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
      <dt className="text-xs font-semibold tracking-wide text-slate-400 uppercase">{label}</dt>
      <dd className="mt-1 text-xl font-semibold text-slate-50 tabular-nums">{children}</dd>
      {note && <p className="mt-1 text-xs text-slate-400">{note}</p>}
    </div>
  );
}

function PipelineRow({ entry }: { entry: PipelineUsage }) {
  const cost = describeCost(entry.usage);
  return (
    <li className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3">
      <span className="min-w-0 text-sm font-medium break-words text-slate-100">
        {entry.pipeline_name}
        {entry.pipeline_id === null && (
          <span className="ml-2 text-xs font-normal text-slate-400">(deleted)</span>
        )}
      </span>
      <span className="text-xs text-slate-400 tabular-nums">
        {entry.runs === 1 ? '1 run' : `${formatCount(entry.runs)} runs`} ·{' '}
        {formatCount(totalTokens(entry.usage))} tokens
      </span>
      <span className="text-sm text-slate-200">
        {cost ? <CostText view={cost} compact /> : 'No usage'}
      </span>
    </li>
  );
}
