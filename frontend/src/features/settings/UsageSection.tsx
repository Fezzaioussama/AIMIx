import type { ReactNode } from 'react';

import type { DayUsage, PipelineUsage, Usage, UsageReport } from '../../core/api/types';
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
    <section aria-labelledby="usage-heading" className="mt-8">
      <h2 id="usage-heading" className="text-2xl font-bold tracking-tight">
        Usage
      </h2>
      <p className="mt-2 mb-6 text-sm text-slate-400">
        What your runs, chats and planning used in the last {USAGE_DAYS} days, and what their model
        calls cost.
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
  return (
    <>
      <TodayLine today={report.today} />
      {report.runs === 0 && totalTokens(report.other) === 0 ? (
        <p className="text-sm text-slate-400">No runs in the last {report.days} days.</p>
      ) : (
        <Totals report={report} />
      )}
    </>
  );
}

/** "$0.12", "1,234 tokens" (no known cost) or "nothing yet". */
function spentWords(spent: Usage): string {
  if (totalTokens(spent) === 0) return 'nothing yet';
  return spent.cost_usd !== null
    ? formatCost(spent.cost_usd)
    : `${formatCount(totalTokens(spent))} tokens`;
}

/** Today's spending, against the daily allowance of the server's key when one applies. */
function TodayLine({ today }: { today: DayUsage }) {
  const limit =
    today.max_cost_usd !== null
      ? formatCost(today.max_cost_usd)
      : today.max_tokens !== null
        ? `${formatCount(today.max_tokens)}-token`
        : null;
  return (
    <p className="mb-4 text-sm text-slate-300">
      {limit
        ? `Today: ${spentWords(today.spent)} of the ${limit} daily allowance of the server's key. It resets at midnight UTC; a key of your own (Providers) has no allowance.`
        : `Today: ${spentWords(today.spent)}.`}
    </p>
  );
}

function Totals({ report }: { report: UsageReport }) {
  const cost = describeCost(report.usage);
  return (
    <>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Stat label="Runs">{formatCount(report.runs)}</Stat>
        <Stat label="Cost">
          {cost ? <CostText view={cost} compact /> : formatCost(report.usage.cost_usd ?? 0)}
        </Stat>
        <Stat
          label="Tokens"
          note={tokenBreakdown(report.usage)}
          className="col-span-2 sm:col-span-1"
        >
          {formatCount(totalTokens(report.usage))}
        </Stat>
      </dl>
      {!report.usage.cost_complete && (
        <p className="mt-3 text-xs text-slate-400">
          Some runs used models whose cost is unknown, so the real cost is higher.
        </p>
      )}
      {totalTokens(report.other) > 0 && (
        <p className="mt-3 text-xs text-slate-400">
          Chats and planning: {formatCost(report.other.cost_usd ?? 0)} (
          {formatCount(totalTokens(report.other))} tokens), counted above.
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
  /** Layout classes for the tile (e.g. spanning the row on a phone). */
  className?: string;
  children: ReactNode;
}

function Stat({ label, note, className = '', children }: StatProps) {
  return (
    <div className={`rounded-2xl border border-white/10 bg-white/[0.03] p-4 ${className}`}>
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
      <span className="ml-auto flex items-baseline gap-4">
        <span className="text-xs text-slate-400 tabular-nums">
          {entry.runs === 1 ? '1 run' : `${formatCount(entry.runs)} runs`} ·{' '}
          {formatCount(totalTokens(entry.usage))} tokens
        </span>
        <span className="min-w-24 text-right text-sm text-slate-200">
          {cost ? <CostText view={cost} compact /> : 'No usage'}
        </span>
      </span>
    </li>
  );
}
