import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { expect } from 'vitest';

import { DOCUMENTS_INPUT_NAME } from '../../core/api/pipelines';
import type { ExtractedDocument, Pipeline } from '../../core/api/types';
import type { StoredMission } from './missionStorage';
import { PLAN, deferred, json } from './testData';
import { useMission } from './useMission';

/** Shared by the specs of the mission's documents: a report, its block, and a mission to
 * attach it to, with the server reading each upload by its name. */
const NOTHING: StoredMission = { messages: [], draft: null };
export const TEXT = 'x'.repeat(2500);
export const report: ExtractedDocument = {
  filename: 'report.pdf',
  format: 'pdf',
  text: TEXT,
  characters: 2500,
  pages: 3,
  truncated: false,
};
export const BLOCK = `[Document: report.pdf]\n${TEXT}`;
export const NOTE = { name: 'report.pdf', pages: 3, characters: 2500 };

const pdf = (name: string) => new File(['%PDF'], name, { type: 'application/pdf' });
export const documentsInput = {
  name: DOCUMENTS_INPUT_NAME,
  label: 'Your documents',
  description: '',
};

/** The server reads each upload by its name: refused, held until the test lets go, or read. */
export function readByName(slow = deferred<Response>()) {
  return (init: RequestInit | undefined) => {
    const name = ((init?.body as FormData).get('file') as File).name;
    if (name === 'bad.pdf') return json({ error: 'document_unreadable', detail: 'No text.' }, 422);
    if (name === 'slow.pdf') return slow.promise;
    return { ...report, filename: name };
  };
}

function wrapper({ children }: { children: ReactNode }) {
  return <MemoryRouter initialEntries={['/mission']}>{children}</MemoryRouter>;
}

export function renderMission(seed = NOTHING, routeId?: number) {
  return renderHook(() => useMission(routeId, seed), { wrapper });
}

type Hook = ReturnType<typeof renderMission>;

export async function attach(hook: Hook, names: string[], settled: (string | undefined)[]) {
  act(() => hook.result.current.documents.addFiles(names.map(pdf)));
  await waitFor(() =>
    expect(hook.result.current.documents.items.map((item) => item.state)).toEqual(settled),
  );
}

export const withInputs = (inputs: Pipeline['inputs']): StoredMission => ({
  messages: [],
  draft: { ...PLAN, inputs },
});
