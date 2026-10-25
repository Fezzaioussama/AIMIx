import { describe, expect, it } from 'vitest';

import type { PipelineChange } from '../../core/api/types';
import { adoptRevision, describeChange } from './revision';
import { draft, revision } from './revisionTestData';

function change(overrides: Partial<PipelineChange>): PipelineChange {
  return { target: 'step', kind: 'changed', label: 'Research', order: 1, fields: [], ...overrides };
}

describe('describeChange', () => {
  it('says what happens to a step in plain words', () => {
    expect(describeChange(change({ kind: 'added', label: 'SEO keywords' }))).toBe(
      'Adds the step “SEO keywords”',
    );
    expect(describeChange(change({ kind: 'removed' }))).toBe('Removes the step “Research”');
    expect(describeChange(change({ fields: ['prompt', 'allowed_tools', 'stage'] }))).toBe(
      'Changes the step “Research”: instructions, tools and when it runs',
    );
  });

  it('describes inputs and a renamed pipeline', () => {
    expect(describeChange(change({ target: 'input', label: 'topic', fields: ['label'] }))).toBe(
      'Changes the input “topic”: label',
    );
    expect(
      describeChange(change({ target: 'pipeline', label: 'Launch kit v2', fields: ['name'] })),
    ).toBe('Renames the pipeline to “Launch kit v2”');
  });

  it('names a changed condition and review loop in plain words', () => {
    expect(describeChange(change({ label: 'SEO', fields: ['condition'] }))).toBe(
      'Changes the step “SEO”: its condition',
    );
    expect(describeChange(change({ label: 'QA', fields: ['prompt', 'review'] }))).toBe(
      'Changes the step “QA”: instructions and its review loop',
    );
    expect(describeChange(change({ label: 'QA', fields: ['condition', 'review'] }))).toBe(
      'Changes the step “QA”: its condition and its review loop',
    );
  });

  it('keeps a field it has no words for readable', () => {
    expect(describeChange(change({ fields: ['is_output', 'new_field'] }))).toBe(
      'Changes the step “Research”: whether it is an output and new field',
    );
  });
});

describe('adoptRevision', () => {
  it('keeps the draft identity so a save updates the same pipeline', () => {
    const adopted = adoptRevision(draft, revision.revised_pipeline);
    expect(adopted.id).toBe(7);
    expect(adopted.steps).toHaveLength(3);
  });

  it('leaves an unsaved draft unsaved', () => {
    const adopted = adoptRevision({ ...draft, id: undefined }, revision.revised_pipeline);
    expect(adopted.id).toBeUndefined();
  });
});
