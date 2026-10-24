import { describe, expect, it } from 'vitest';

import {
  draftFrom,
  draftProblem,
  emptyDraft,
  hostOf,
  toCreate,
  toIntegrationName,
  toPatch,
} from './integrationDraft';
import type { IntegrationDraft } from './integrationDraft';
import { INTEGRATION } from './testData';

const NEW: IntegrationDraft = {
  name: 'crm',
  url: ' https://mcp.crm.example/mcp ',
  headers: [
    { name: ' Authorization ', value: ' Bearer key-1234 ', saved: null },
    { name: '', value: '', saved: null },
  ],
};

describe('integration drafts', () => {
  it('types names as snake_case and shows hosts', () => {
    expect(toIntegrationName('My CRM-Tools!')).toBe('my_crm_tools');
    expect(toIntegrationName('x'.repeat(40))).toHaveLength(31);
    expect(hostOf('https://mcp.crm.example:8443/mcp')).toBe('mcp.crm.example:8443');
    expect(hostOf('not a url')).toBe('not a url');
  });

  it('sends a new integration trimmed, without blank header rows', () => {
    expect(draftProblem(NEW, null)).toBeNull();
    expect(toCreate(NEW)).toEqual({
      name: 'crm',
      url: 'https://mcp.crm.example/mcp',
      headers: [{ name: 'Authorization', value: 'Bearer key-1234' }],
    });
  });

  it.each([
    [{ name: 'C' }, /2 to 31 characters/],
    [{ url: 'mcp.crm.example' }, /full server URL/],
    [{ headers: [{ name: '', value: 'v', saved: null }] }, /every header a name/],
    [{ headers: [{ name: 'X-Key', value: '', saved: null }] }, /every new header a value/],
    [
      {
        headers: [
          { name: 'X-Key', value: 'a', saved: null },
          { name: 'x-key', value: 'b', saved: null },
        ],
      },
      /only once/,
    ],
  ])('explains what blocks saving: %o', (change, problem) => {
    expect(draftProblem({ ...emptyDraft(), ...NEW, ...change }, null)).toMatch(problem);
  });

  it('keeps a saved value left blank and sends only what changed', () => {
    const draft = draftFrom(INTEGRATION);
    expect(draft.headers).toEqual([
      { name: 'Authorization', value: '', saved: INTEGRATION.headers[0] },
    ]);
    expect(draftProblem(draft, INTEGRATION)).toBeNull();
    expect(toPatch(draft, INTEGRATION)).toEqual({});

    const renamed = { ...draft, name: 'sales' };
    expect(toPatch(renamed, INTEGRATION)).toEqual({ name: 'sales' });

    const added = {
      ...draft,
      headers: [...draft.headers, { name: 'X-Team', value: 'ops', saved: null }],
    };
    expect(toPatch(added, INTEGRATION)).toEqual({
      headers: [{ name: 'Authorization' }, { name: 'X-Team', value: 'ops' }],
    });
  });

  it('asks for every value again when the server address changes', () => {
    const moved = { ...draftFrom(INTEGRATION), url: 'https://elsewhere.example/mcp' };
    expect(draftProblem(moved, INTEGRATION)).toMatch(/enter every header value again/);

    const retyped = { ...moved, headers: [{ ...moved.headers[0], value: 'Bearer new' }] };
    expect(draftProblem(retyped, INTEGRATION)).toBeNull();
    expect(toPatch(retyped, INTEGRATION)).toEqual({
      url: 'https://elsewhere.example/mcp',
      headers: [{ name: 'Authorization', value: 'Bearer new' }],
    });
  });

  it('needs the value again once a saved header is renamed', () => {
    const draft = draftFrom(INTEGRATION);
    const renamed = { ...draft, headers: [{ ...draft.headers[0], name: 'X-Api-Key' }] };
    expect(draftProblem(renamed, INTEGRATION)).toMatch(/every new header a value/);
  });
});
