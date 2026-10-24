import { useCallback, useState } from 'react';

export interface Notice {
  kind: 'success' | 'error';
  text: string;
}

export type SubmissionStatus = 'loading' | 'idle' | 'saving';

/** The backend's message when there is one (see core/api/client.ts), else `fallback`. */
export function errorText(cause: unknown, fallback: string): string {
  return cause instanceof Error ? cause.message : fallback;
}

/**
 * One busy flag and one notice for a Settings section, shared by its hooks:
 * `submit` runs a task, then says it worked or why it did not.
 */
export function useSubmission(initial: SubmissionStatus) {
  const [status, setStatus] = useState<SubmissionStatus>(initial);
  const [notice, setNotice] = useState<Notice | null>(null);

  const submit = useCallback(
    async (task: () => Promise<void>, done: string, failed: string): Promise<boolean> => {
      setStatus('saving');
      setNotice(null);
      try {
        await task();
        setNotice({ kind: 'success', text: done });
        return true;
      } catch (cause) {
        setNotice({ kind: 'error', text: errorText(cause, failed) });
        return false;
      } finally {
        setStatus('idle');
      }
    },
    [],
  );

  return { status, setStatus, notice, setNotice, submit };
}

export type Submission = ReturnType<typeof useSubmission>;
