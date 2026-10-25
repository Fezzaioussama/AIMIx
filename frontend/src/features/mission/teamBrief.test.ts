import { describe, expect, it } from 'vitest';

import type { Pipeline } from '../../core/api/types';
import { countOf, describeTeam, providesInWords, toolsInWords } from './teamBrief';
import { PLAN, planStep } from './testData';

describe('describeTeam', () => {
  it('names each agent by its role and says what it delivers', () => {
    const brief = describeTeam(PLAN);

    expect(brief.name).toBe('Competitor brief');
    expect(brief.stages).toBe(2);
    expect(brief.agents.map((agent) => agent.name)).toEqual(['Researcher', 'Analyst']);
    expect(brief.agents[0]).toMatchObject({ task: 'Market research result', deliverable: false });
    expect(brief.agents[1]).toMatchObject({ deliverable: true });
  });

  it('falls back to the step title, then to the start of its prompt', () => {
    const team: Pipeline = {
      name: 'x',
      inputs: [],
      steps: [
        { ...planStep(1, 1, 'Collect', false), role: '', expected_output: '' },
        {
          ...planStep(2, 2, 'Write', true),
          role: 'Writer',
          expected_output: '',
          prompt: `Write   a long\nreport ${'word '.repeat(60)}`,
        },
        { ...planStep(3, 3, '', true), role: '', expected_output: '', prompt: '  ' },
      ],
    };

    const [collect, write, bare] = describeTeam(team).agents;

    expect(collect.name).toBe('Collect');
    expect(collect.task).toBe('Collect for {company}: {input}');
    expect(write.task).toBe('Write');
    expect(bare.name).toBe('Step 3');
    expect(bare.task).toBe('Works on what the previous agents hand over.');
  });

  it('cuts a long prompt used as the task', () => {
    const team: Pipeline = {
      name: 'x',
      inputs: [],
      steps: [
        { ...planStep(1, 1, '', true), role: '', expected_output: '', prompt: 'a'.repeat(300) },
      ],
    };

    const { task } = describeTeam(team).agents[0];

    expect(task.endsWith('…')).toBe(true);
    expect(task.length).toBeLessThan(160);
  });

  it('marks the last stage as the deliverable when no step is marked', () => {
    const team: Pipeline = {
      name: 'x',
      inputs: [],
      steps: [planStep(1, 1, 'A', false), planStep(2, 2, 'B', false)],
    };

    expect(describeTeam(team).agents.map((agent) => agent.deliverable)).toEqual([false, true]);
  });

  it('lists what the person provides by label', () => {
    expect(describeTeam(PLAN).provides).toEqual(['Your company']);
    expect(describeTeam({ ...PLAN, inputs: [] }).provides).toEqual([]);
  });
});

describe('words for the brief', () => {
  it('says which tools an agent may use', () => {
    expect(toolsInWords({ kind: 'all', names: [] })).toBe('Can use any of your tools');
    expect(toolsInWords({ kind: 'none', names: [] })).toBe('Works without tools');
    expect(toolsInWords({ kind: 'some', names: ['web_search'] })).toBe('Uses web search');
    expect(toolsInWords({ kind: 'some', names: ['web_search', 'calculator', 'clock'] })).toBe(
      'Uses web search, calculator and clock',
    );
  });

  it('says what the person provides, with or without named inputs', () => {
    expect(providesInWords(describeTeam(PLAN))).toBe('You provide: Your company.');
    expect(providesInWords(describeTeam({ ...PLAN, inputs: [] }))).toBe(
      'You provide: a short description of what to work on.',
    );
  });

  it('counts with the right plural', () => {
    expect(countOf(1, 'agent')).toBe('1 agent');
    expect(countOf(3, 'stage')).toBe('3 stages');
  });
});
