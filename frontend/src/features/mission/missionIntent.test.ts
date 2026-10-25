import { describe, expect, it } from 'vitest';

import { isRunRequest } from './missionIntent';

describe('isRunRequest', () => {
  it.each([
    'Run it',
    'run it!',
    'RUN IT NOW',
    'run',
    'Go ahead',
    'let’s go',
    "lets go",
    'ok, run it please',
    'Please run it.',
    'start the mission',
    'launch it',
    '  do it  ',
  ])('treats "%s" as a request to run', (text) => {
    expect(isRunRequest(text)).toBe(true);
  });

  it.each([
    'Run the research steps in parallel',
    'Add an agent that runs a fact check',
    'Make it shorter',
    'start with a summary of the competitors',
    'do not run it yet',
    '',
    '   ',
  ])('leaves "%s" as a change to the team', (text) => {
    expect(isRunRequest(text)).toBe(false);
  });
});
