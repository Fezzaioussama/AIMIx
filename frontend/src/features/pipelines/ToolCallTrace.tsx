import type { StepResult } from '../../core/api/types';

interface ToolCallTraceProps {
  calls: StepResult['tool_calls'];
}

/** Shows tool use without exposing arguments or tool response contents. */
export function ToolCallTrace({ calls }: ToolCallTraceProps) {
  if (calls.length === 0) return null;

  return (
    <details className="mt-2 rounded-lg border border-white/10 bg-slate-900/50 px-4 py-3 text-xs">
      <summary className="cursor-pointer text-slate-300">Tools used ({calls.length})</summary>
      <ul className="mt-2 space-y-1">
        {calls.map((call, index) => (
          <li key={`${call.name}-${index}`} className="flex items-center justify-between gap-3">
            <span className="break-all text-slate-200">{call.name}</span>
            <span className={call.status === 'success' ? 'text-emerald-300' : 'text-red-300'}>
              {call.status === 'success' ? 'Success' : 'Error'}
            </span>
          </li>
        ))}
      </ul>
    </details>
  );
}
