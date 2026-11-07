import { describe, expect, it } from 'vitest';

import type { StepResult } from '../../core/api/types';
import { makeApproval } from './testData';
import {
  approvalAsk,
  approvalHeading,
  isPlainAsk,
  TOOL_WORDS,
  toolTargetLines,
  toolUsePhrase,
} from './toolWords';

type Calls = StepResult['tool_calls'];

const ok = (name: string, target = '') => ({ name, status: 'success' as const, target });
const failed = (name: string, target = '') => ({ name, status: 'error' as const, target });

describe('toolUsePhrase', () => {
  it('counts each tool in the order it was first used, with its failures', () => {
    const research: Calls = [
      ok('current_datetime'),
      ok('web_search'),
      ok('fetch_url'),
      failed('fetch_url'),
      ok('web_search'),
      ok('fetch_url'),
      ok('web_search'),
    ];

    expect(toolUsePhrase(research)).toBe('1 date check · 3 web searches · 3 page reads, 1 failed');
  });

  it('says one and several in their own words', () => {
    expect(toolUsePhrase([ok('save_artifact')])).toBe('1 file saved');
    expect(toolUsePhrase([ok('save_artifact'), ok('save_artifact')])).toBe('2 files saved');
    expect(toolUsePhrase([ok('generate_image'), ok('find_objects')])).toBe(
      '1 picture drawn · 1 object count',
    );
  });

  it('names a tool it has no words for by its name', () => {
    const calls: Calls = [ok('crm_send_email'), failed('crm_send_email')];

    expect(toolUsePhrase(calls)).toBe('Crm send email (2, 1 failed)');
    expect(toolUsePhrase([ok('docs_search')])).toBe('Docs search (1)');
  });

  it('does not mistake an object property for a tool', () => {
    expect(toolUsePhrase([ok('constructor')])).toBe('Constructor (1)');
  });

  it('is null when no tool was used', () => {
    expect(toolUsePhrase([])).toBeNull();
  });
});

describe('TOOL_WORDS', () => {
  it('has a plain ask for every built-in tool', () => {
    for (const words of Object.values(TOOL_WORDS)) {
      expect(words.ask?.({})).toMatch(/^[a-z]/);
    }
  });
});

describe('approvalAsk', () => {
  const builtIn = (tool_name: string, args: Record<string, unknown>) =>
    makeApproval({ tool_name, tool_source: 'AIMIx', arguments: args });

  it('asks for a built-in tool in plain words, filled from its arguments', () => {
    const save = builtIn('save_artifact', { path: 'loyalty/linkedin-post.md', content: 'x' });

    expect(approvalAsk(save)).toBe('save “loyalty/linkedin-post.md” to your files');
    expect(approvalAsk(builtIn('web_search', { query: 'loyalty apps' }))).toBe(
      'search the web for “loyalty apps”',
    );
    expect(approvalAsk(builtIn('fetch_url', { url: 'https://example.com/a' }))).toBe(
      'open the web page https://example.com/a',
    );
    expect(approvalAsk(builtIn('find_objects', { image_path: 'shelf.jpg', what: 'loaf' }))).toBe(
      'look for “loaf” in “shelf.jpg”',
    );
    expect(approvalAsk(builtIn('current_datetime', {}))).toBe('check today’s date');
  });

  it('falls back to the generic request when an argument is missing or not text', () => {
    expect(approvalAsk(builtIn('save_artifact', { content: 'x' }))).toBe(
      'save a file to your files',
    );
    expect(approvalAsk(builtIn('web_search', { query: '  ' }))).toBe('search the web');
    expect(approvalAsk(builtIn('read_csv', { path: 3 }))).toBe('read a spreadsheet');
    expect(approvalAsk(builtIn('find_objects', { what: 'loaf' }))).toBe(
      'look for something in a picture',
    );
  });

  it('names an integration or MCP tool and where it comes from', () => {
    expect(approvalAsk(makeApproval())).toBe('use “Send email” from crm');
    expect(approvalAsk(makeApproval({ tool_name: 'docs_search', tool_source: 'MCP' }))).toBe(
      'use “Docs search” from MCP',
    );
  });

  it('uses plain words only for AIMIx’s own tools', () => {
    const lookalike = makeApproval({ tool_name: 'save_artifact', tool_source: 'MCP' });

    expect(isPlainAsk(lookalike)).toBe(false);
    expect(approvalAsk(lookalike)).toBe('use “Save artifact” from MCP');
    expect(approvalAsk(builtIn('brand_new_tool', {}))).toBe('use “Brand new tool”');
    expect(isPlainAsk(builtIn('save_artifact', {}))).toBe(true);
  });
});

describe('approvalHeading', () => {
  it('asks a built-in tool’s request as a question', () => {
    const save = makeApproval({
      tool_name: 'save_artifact',
      tool_source: 'AIMIx',
      arguments: { path: 'notes/plan.md', content: 'x' },
    });

    expect(approvalHeading(save)).toBe('Save “notes/plan.md” to your files?');
  });

  it('asks to allow any other tool by its name', () => {
    expect(approvalHeading(makeApproval())).toBe('Allow “Send email”?');
  });
});

describe('toolTargetLines', () => {
  it('says what each call was about, in the tool’s words, and marks a failed one', () => {
    const calls: Calls = [
      ok('web_search', 'best CRM 2026'),
      failed('fetch_url', 'https://example.com/pricing'),
      ok('calculator'),
      ok('crm_send_email', 'ada@example.com'),
    ];

    expect(toolTargetLines(calls)).toEqual([
      'web search “best CRM 2026”',
      'page read “https://example.com/pricing” (failed)',
      'crm send email “ada@example.com”',
    ]);
  });
});
