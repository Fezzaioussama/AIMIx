import type { Run } from '../../core/api/types';
import { BusyNotice } from '../../core/ui/BusyNotice';
import { inputLabel } from '../pipelines/pipelineInputs';
import { DeleteRunButton } from './DeleteRunButton';
import { LiveRun } from './LiveRun';
import { RunByline } from './RunByline';
import { isActive } from './runStatus';
import type { LiveRunState } from './useRun';

/** Inputs longer than this start folded. */
const OPEN_INPUTS_MAX_CHARS = 600;

interface RunDetailProps {
  live: LiveRunState;
  onDelete: () => void;
  deleting: boolean;
}

/** One run from the history: what it was given, then the live run itself. */
export function RunDetail({ live, onDelete, deleting }: RunDetailProps) {
  const { run } = live;
  if (run === null) {
    return live.error ? (
      <p role="alert" className="rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-300">
        {live.error}
      </p>
    ) : (
      <BusyNotice className="mt-12">Loading the run…</BusyNotice>
    );
  }
  return (
    <article aria-labelledby="run-title">
      <header className="mb-6">
        <p className="mb-1 text-xs font-semibold tracking-widest text-sky-300 uppercase">
          Run #{run.id}
        </p>
        <h1 id="run-title" className="text-2xl font-bold tracking-tight break-words">
          {run.pipeline_name}
        </h1>
        <RunByline run={run} />
      </header>
      <LiveRun
        run={run}
        onStop={() => void live.stop()}
        onResume={() => void live.resume()}
        busy={live.busy}
        error={live.error}
        actions={
          isActive(run.status) ? undefined : <DeleteRunButton onDelete={onDelete} busy={deleting} />
        }
      >
        <RunInputs run={run} />
      </LiveRun>
    </article>
  );
}

/** What the run was given: its free text, or each named input's value. */
function RunInputs({ run }: { run: Run }) {
  const named = run.definition.inputs.length > 0;
  const entries = named
    ? run.definition.inputs.map((field) => [inputLabel(field), run.inputs[field.name] ?? ''])
    : [['Input', run.input]];
  const size = entries.reduce((sum, [, value]) => sum + value.length, 0);
  return (
    <details
      open={size <= OPEN_INPUTS_MAX_CHARS}
      className="mt-4 rounded-2xl border border-white/10 bg-slate-900/60 px-4 py-3"
    >
      <summary className="cursor-pointer text-sm font-medium text-slate-200 select-none">
        {named ? `Inputs (${entries.length})` : 'Input'}
      </summary>
      <dl className="mt-3 space-y-3">
        {entries.map(([label, value]) => (
          <div key={label}>
            {/* One free-text input is already named by the summary. */}
            <dt
              className={
                named ? 'text-xs font-semibold tracking-wide text-slate-400 uppercase' : 'sr-only'
              }
            >
              {label}
            </dt>
            <dd className="mt-1 max-h-60 overflow-auto text-sm whitespace-pre-wrap text-slate-200">
              {value}
            </dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
