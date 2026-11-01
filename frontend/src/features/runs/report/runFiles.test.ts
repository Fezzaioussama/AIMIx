import { describe, expect, it } from 'vitest';

import type { PipelineStep, Run, WorkspaceFile } from '../../../core/api/types';
import { makeRun } from '../testData';
import { mayHaveSavedFiles, savedDuringRun } from './runFiles';

function withTools(allowed: string[] | null, overrides: Partial<Run> = {}): Run {
  const run = makeRun(overrides);
  const steps = run.definition.steps.map((step): PipelineStep => ({
    ...step,
    allowed_tools: step.order === 2 ? allowed : [],
  }));
  return { ...run, definition: { ...run.definition, steps } };
}

function file(path: string, modifiedAt: string, type = 'md'): WorkspaceFile {
  return { path, size: 10, modified_at: modifiedAt, type };
}

describe('mayHaveSavedFiles', () => {
  it.each<[string, string[] | null, boolean]>([
    ['every tool', null, true],
    ['no tool', [], false],
    ['only web search', ['web_search'], false],
    ['save_artifact', ['save_artifact'], true],
    ['generate_image', ['generate_image', 'web_search'], true],
    ['find_objects', ['find_objects'], true],
    ['run_python', ['run_python'], true],
  ])('%s', (_name, allowed, may) => {
    expect(mayHaveSavedFiles(withTools(allowed))).toBe(may);
  });

  it('is false for a run that has not started', () => {
    expect(mayHaveSavedFiles(withTools(null, { status: 'queued', started_at: null }))).toBe(false);
  });
});

describe('savedDuringRun', () => {
  // The run worked from 10:00:00 to 10:05:00.
  const ended = makeRun({ status: 'succeeded', finished_at: '2026-10-24T10:05:00Z' });

  it('keeps the files modified while the run worked, with 2 s either side', () => {
    const files = [
      file('early.md', '2026-10-24T09:59:57.999Z'),
      file('edge-start.md', '2026-10-24T09:59:58Z'),
      file('middle.md', '2026-10-24T10:02:00Z'),
      file('edge-end.md', '2026-10-24T10:05:02Z'),
      file('late.md', '2026-10-24T10:05:02.001Z'),
    ];
    expect(savedDuringRun(files, ended).map((item) => item.path)).toEqual([
      'edge-end.md',
      'middle.md',
      'edge-start.md',
    ]);
  });

  it('leaves the window open while the run still works, whatever the browser’s clock says', () => {
    // Saved by the server at 10:09; the browser's clock may read 10:08 (it runs behind).
    const files = [
      file('early.md', '2026-10-24T09:59:00Z'),
      file('new.md', '2026-10-24T10:09:00Z'),
    ];
    expect(savedDuringRun(files, makeRun()).map((item) => item.path)).toEqual(['new.md']);
  });

  it('puts pictures first, then the newest', () => {
    const files = [
      file('old.md', '2026-10-24T10:01:00Z'),
      file('chart.png', '2026-10-24T10:02:00Z', 'png'),
      file('new.md', '2026-10-24T10:03:00Z'),
      file('hero.jpg', '2026-10-24T10:04:00Z', 'jpg'),
    ];
    expect(savedDuringRun(files, ended).map((item) => item.path)).toEqual([
      'hero.jpg',
      'chart.png',
      'new.md',
      'old.md',
    ]);
  });

  it('has none for a run that has not started', () => {
    const queued = makeRun({ status: 'queued', started_at: null });
    expect(savedDuringRun([file('a.md', '2026-10-24T10:00:00Z')], queued)).toEqual([]);
  });
});
