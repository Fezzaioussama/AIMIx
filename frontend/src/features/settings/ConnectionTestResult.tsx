import type { IntegrationTool } from '../../core/api/types';
import { Spinner } from '../../core/ui/Spinner';
import type { ConnectionTest } from './useIntegrations';

export function toolCount(count: number): string {
  return count === 1 ? '1 tool' : `${count} tools`;
}

function ToolList({ tools }: { tools: IntegrationTool[] }) {
  if (tools.length === 0) {
    return <p className="text-slate-300">Connected, but the server offers no tools.</p>;
  }
  return (
    <>
      <p className="text-emerald-400">Connected. Found {toolCount(tools.length)}:</p>
      <ul className="mt-2 max-h-56 space-y-1.5 overflow-y-auto rounded-lg border border-white/10 bg-slate-950/40 p-2">
        {tools.map((tool) => (
          <li key={tool.name} className="min-w-0 text-xs">
            <span className="font-mono break-all text-sky-200">{tool.name}</span>
            {tool.description && <span className="block text-slate-400">{tool.description}</span>}
          </li>
        ))}
      </ul>
    </>
  );
}

/** The last "Test connection" of one integration; announced as it changes. */
export function ConnectionTestResult({ name, test }: { name: string; test?: ConnectionTest }) {
  return (
    // Always rendered, so screen readers already follow the region when results arrive.
    <div aria-live="polite" className="text-sm">
      {test?.status === 'testing' && (
        <p className="mt-3 flex items-center gap-2 text-slate-300">
          <Spinner decorative className="size-4" />
          Connecting to {name}…
        </p>
      )}
      {test?.status === 'failed' && <p className="mt-3 text-red-400">{test.error}</p>}
      {test?.status === 'passed' && (
        <div className="mt-3">
          <ToolList tools={test.tools} />
        </div>
      )}
    </div>
  );
}
