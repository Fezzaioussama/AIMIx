/**
 * AIMIx's own tools in plain words: what an agent's tool use amounts to ("3 web
 * searches · 3 page reads, 1 failed"), and what an approval asks for ("save
 * “notes/plan.md” to your files"). A registry keyed by tool name (Strategy +
 * Registry, AGENTS §7): a new built-in tool is a new entry, never a new branch.
 */
import type { RunApproval, StepResult } from '../../core/api/types';
import { capitalised, toolLabel } from './approvalFormat';

/** Where AIMIx's own tools come from (`tool_catalog.NATIVE_SOURCE` on the server). */
const NATIVE_SOURCE = 'AIMIx';

type ToolArgs = Record<string, unknown>;
type ToolCalls = StepResult['tool_calls'];

interface ToolWords {
  /** One use: "1 web search". */
  one: string;
  /** Several: "3 web searches". */
  many: string;
  /** What an approval of it asks, filled from the call's arguments. */
  ask?: (args: ToolArgs) => string;
}

/** A text argument, trimmed; null when it is missing, empty or not text. */
function textArg(args: ToolArgs, key: string): string | null {
  const value = args[key];
  return typeof value === 'string' && value.trim() !== '' ? value.trim() : null;
}

/** An ask that names one argument, or says the generic thing when it is missing. */
function askWith(key: string, filled: (value: string) => string, generic: string) {
  return (args: ToolArgs) => {
    const value = textArg(args, key);
    return value === null ? generic : filled(value);
  };
}

function findObjectsAsk(args: ToolArgs): string {
  const what = textArg(args, 'what');
  const picture = textArg(args, 'image_path');
  return what !== null && picture !== null
    ? `look for “${what}” in “${picture}”`
    : 'look for something in a picture';
}

/** By the names in `backend/api/services/toolbox/tools.py` and `agent_tools.py`. */
export const TOOL_WORDS: Record<string, ToolWords> = {
  web_search: {
    one: 'web search',
    many: 'web searches',
    ask: askWith('query', (query) => `search the web for “${query}”`, 'search the web'),
  },
  fetch_url: {
    one: 'page read',
    many: 'page reads',
    ask: askWith('url', (url) => `open the web page ${url}`, 'open a web page'),
  },
  read_workspace_file: {
    one: 'file read',
    many: 'file reads',
    ask: askWith('path', (path) => `read “${path}” from your files`, 'read one of your files'),
  },
  list_workspace_files: {
    one: 'file listing',
    many: 'file listings',
    ask: () => 'look through your files',
  },
  search_workspace_files: {
    one: 'file search',
    many: 'file searches',
    ask: askWith('query', (query) => `search your files for “${query}”`, 'search your files'),
  },
  read_csv: {
    one: 'spreadsheet read',
    many: 'spreadsheet reads',
    ask: askWith('path', (path) => `read the spreadsheet “${path}”`, 'read a spreadsheet'),
  },
  save_artifact: {
    one: 'file saved',
    many: 'files saved',
    ask: askWith('path', (path) => `save “${path}” to your files`, 'save a file to your files'),
  },
  generate_image: {
    one: 'picture drawn',
    many: 'pictures drawn',
    ask: askWith(
      'path',
      (path) => `draw a picture and save it as “${path}”`,
      'draw a picture and save it to your files',
    ),
  },
  find_objects: { one: 'object count', many: 'object counts', ask: findObjectsAsk },
  run_python: { one: 'code run', many: 'code runs', ask: () => 'run code in a sandbox' },
  ask_user: {
    one: 'question asked',
    many: 'questions asked',
    ask: askWith('question', (question) => `ask you “${question}”`, 'ask you a question'),
  },
  calculator: { one: 'calculation', many: 'calculations', ask: () => 'do a calculation' },
  current_datetime: { one: 'date check', many: 'date checks', ask: () => 'check today’s date' },
  list_pipelines: {
    one: 'pipeline listing',
    many: 'pipeline listings',
    ask: () => 'look through your pipelines',
  },
  inspect_pipeline: {
    one: 'pipeline read',
    many: 'pipeline reads',
    ask: () => 'read one of your pipelines',
  },
};

function wordsFor(name: string): ToolWords | undefined {
  return Object.hasOwn(TOOL_WORDS, name) ? TOOL_WORDS[name] : undefined;
}

/** Where the tool comes from, as a phrase; AIMIx's own tools need no source. */
export function fromSource(source: string): string {
  return source === NATIVE_SOURCE ? '' : ` from ${source}`;
}

interface Tally {
  name: string;
  uses: number;
  failed: number;
}

/** Uses and failures per tool, in the order each tool was first used. */
function tally(calls: ToolCalls): Tally[] {
  const byName = new Map<string, Tally>();
  for (const call of calls) {
    const entry = byName.get(call.name) ?? { name: call.name, uses: 0, failed: 0 };
    entry.uses += 1;
    if (call.status === 'error') entry.failed += 1;
    byName.set(call.name, entry);
  }
  return [...byName.values()];
}

function tallyWords({ name, uses, failed }: Tally): string {
  const failures = failed > 0 ? `, ${failed} failed` : '';
  const words = wordsFor(name);
  if (words === undefined) return `${toolLabel(name, '')} (${uses}${failures})`;
  return `${uses} ${uses === 1 ? words.one : words.many}${failures}`;
}

/** "1 date check · 3 web searches · 3 page reads, 1 failed"; null when no tool was used. */
export function toolUsePhrase(calls: ToolCalls): string | null {
  if (calls.length === 0) return null;
  return tally(calls).map(tallyWords).join(' · ');
}

/**
 * What each call was about, with its tool: 'web search “best CRM 2026”', 'page read
 * https://… (failed)'. A call with no subject (a calculation, code) is left out.
 */
export function toolTargetLines(calls: ToolCalls): string[] {
  return calls
    .filter((call) => call.target !== '')
    .map((call) => {
      const tool = wordsFor(call.name)?.one ?? toolLabel(call.name, '').toLowerCase();
      return `${tool} “${call.target}”${call.status === 'error' ? ' (failed)' : ''}`;
    });
}

/** The plain words of an approval's tool, for AIMIx's own tools that have them. */
function plainAsk(approval: RunApproval): ToolWords['ask'] {
  if (approval.tool_source !== NATIVE_SOURCE) return undefined;
  return wordsFor(approval.tool_name)?.ask;
}

/** Whether the approval can be asked in plain words (a built-in tool). */
export function isPlainAsk(approval: RunApproval): boolean {
  return plainAsk(approval) !== undefined;
}

/**
 * What the approval asks for, to follow "wants to": 'save “notes/plan.md” to your
 * files', or 'use “Send email” from crm' for an integration or MCP tool.
 */
export function approvalAsk(approval: RunApproval): string {
  const ask = plainAsk(approval);
  if (ask !== undefined) return ask(approval.arguments);
  const label = toolLabel(approval.tool_name, approval.tool_source);
  return `use “${label}”${fromSource(approval.tool_source)}`;
}

/** The card's heading: "Save “notes/plan.md” to your files?" or "Allow “Send email”?". */
export function approvalHeading(approval: RunApproval): string {
  const ask = plainAsk(approval);
  if (ask === undefined) return `Allow “${toolLabel(approval.tool_name, approval.tool_source)}”?`;
  return `${capitalised(ask(approval.arguments))}?`;
}
