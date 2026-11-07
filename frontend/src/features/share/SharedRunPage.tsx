import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { ApiError } from '../../core/api/client';
import { errorMessage } from '../../core/api/errorMessage';
import { getSharedRun } from '../../core/api/runs';
import type { Run } from '../../core/api/types';
import { formatDateTime } from '../../core/time';
import { AmbientBackdrop } from '../../core/ui/AmbientBackdrop';
import { BusyNotice } from '../../core/ui/BusyNotice';
import { FOCUS_RING } from '../../core/ui/focus';
import { GradientText } from '../../core/ui/reactbits/GradientText';
import { RunReport } from '../runs/report/RunReport';

/** What a withdrawn (or made-up) link says; the server's words are the same. */
export const NOT_SHARED = 'This link does not show a run: it may have been withdrawn.';

/** The report a link shows, loaded once; leaving the page cancels the request. */
function useSharedRun(token: string) {
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    getSharedRun(token, controller.signal)
      .then((loaded) => {
        if (!controller.signal.aborted) setRun(loaded);
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        const gone = cause instanceof ApiError && cause.status === 404;
        setError(gone ? NOT_SHARED : errorMessage(cause, 'Could not load this report.'));
      });
    return () => controller.abort();
  }, [token]);

  return { run, error };
}

/** The loaded report under its title, or why there is none. */
function SharedBody({ run, error }: { run: Run | null; error: string }) {
  if (error) {
    return (
      <p role="alert" className="rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-300">
        {error}
      </p>
    );
  }
  if (run === null) return <BusyNotice className="mt-12">Loading the report…</BusyNotice>;
  return (
    <article aria-labelledby="shared-run-title">
      <header className="mb-8">
        <h1 id="shared-run-title" className="text-2xl font-bold tracking-tight break-words">
          {run.pipeline_name}
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Run of {formatDateTime(run.created_at)} · shared with you, read-only
        </p>
      </header>
      <RunReport key={run.id} run={run} level={2} />
    </article>
  );
}

/**
 * `/shared/:token`, public: one run's report for whoever has the link, without an
 * account and without controls (nothing to stop, answer or rate).
 */
export function SharedRunPage() {
  const token = useParams().token ?? '';
  const { run, error } = useSharedRun(token);
  return (
    <div className="relative min-h-screen">
      <AmbientBackdrop />
      <header className="mx-auto flex w-full max-w-[36rem] items-center justify-between gap-4 px-4 py-5">
        <Link to="/" className={`rounded-sm ${FOCUS_RING}`}>
          <GradientText className="text-xl font-extrabold tracking-tight">AIMIx</GradientText>
        </Link>
        <span className="text-xs text-slate-400">A report shared with you</span>
      </header>
      <main className="mx-auto w-full max-w-[36rem] px-4 pb-16">
        <SharedBody run={run} error={error} />
      </main>
    </div>
  );
}
