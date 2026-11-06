import { useCallback, useEffect, useState } from 'react';

import { fetchMemory, saveMemory } from '../../core/api/memory';
import type { Memory } from '../../core/api/memoryTypes';
import { errorText, useSubmission } from './useSubmission';

/**
 * Settings → Memory: loads what the person told AIMIx to keep in mind, holds the text
 * as they edit it, and saves it. `dirty` is whether the text differs from what is saved.
 */
export function useMemory() {
  const [memory, setMemory] = useState<Memory | null>(null);
  const [draft, setDraft] = useState('');
  const { status, setStatus, notice, setNotice, submit } = useSubmission('loading');

  useEffect(() => {
    const controller = new AbortController();
    fetchMemory(controller.signal)
      .then((loaded) => {
        setMemory(loaded);
        setDraft(loaded.instructions);
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted)
          setNotice({ kind: 'error', text: errorText(cause, 'Could not load your memory.') });
      })
      .finally(() => {
        if (!controller.signal.aborted) setStatus('idle');
      });
    return () => controller.abort();
  }, [setNotice, setStatus]);

  const edit = useCallback(
    (text: string) => {
      setDraft(text);
      setNotice(null);
    },
    [setNotice],
  );

  const save = useCallback(
    () =>
      submit(
        async () => {
          const saved = await saveMemory(draft);
          setMemory(saved);
          setDraft(saved.instructions);
        },
        'Memory saved.',
        'Could not save your memory.',
      ),
    [draft, submit],
  );

  const dirty = memory !== null && draft.trim() !== memory.instructions;

  return { memory, draft, status, notice, dirty, edit, save };
}
