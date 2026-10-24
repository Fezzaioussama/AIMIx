import { useCallback, useEffect, useRef, useState } from 'react';

import { errorMessage } from '../../core/api/errorMessage';
import { deleteRun, listRuns } from '../../core/api/runs';
import type { RunSummary } from '../../core/api/types';
import { isActive } from './runStatus';

/** Runs fetched per page of the history. */
export const RUN_PAGE_SIZE = 20;
/** While a listed run is active, the list is fetched again this often. */
export const RUN_LIST_REFRESH_MS = 5000;

/** The fields a summary shares with a whole run, to keep a listed run up to date. */
export function summaryOf(run: RunSummary): RunSummary {
  const { id, pipeline_id, pipeline_name, status, error, created_at, started_at, finished_at } =
    run;
  return { id, pipeline_id, pipeline_name, status, error, created_at, started_at, finished_at };
}

/**
 * The signed-in user's runs, newest first, a page at a time. While any listed
 * run is active the loaded pages are fetched again, so statuses stay current.
 */
export function useRunHistory() {
  const [items, setItems] = useState<RunSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState('');
  // How many runs are listed, for refreshes and the next page (read outside render).
  const shown = useRef(0);
  const mounted = useRef(true);
  const anyActive = items.some((item) => isActive(item.status));

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    shown.current = items.length;
  }, [items.length]);

  // The first page, then the loaded pages again while anything listed is active.
  useEffect(() => {
    const controller = new AbortController();
    const load = () =>
      listRuns({ limit: Math.max(shown.current, RUN_PAGE_SIZE) }, controller.signal)
        .then((page) => {
          setItems(page.items);
          setTotal(page.total);
          setError('');
        })
        .catch((cause: unknown) => {
          if (!controller.signal.aborted)
            setError(errorMessage(cause, 'Could not load your runs.'));
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    let timer: ReturnType<typeof setInterval> | undefined;
    if (anyActive) timer = setInterval(() => void load(), RUN_LIST_REFRESH_MS);
    else if (shown.current === 0) void load();
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, [anyActive]);

  const loadMore = useCallback(async () => {
    setLoadingMore(true);
    try {
      const page = await listRuns({ limit: RUN_PAGE_SIZE, offset: shown.current });
      if (!mounted.current) return;
      setItems((known) => [
        ...known,
        ...page.items.filter((item) => !known.some((seen) => seen.id === item.id)),
      ]);
      setTotal(page.total);
    } catch (cause) {
      if (mounted.current) setError(errorMessage(cause, 'Could not load more runs.'));
    } finally {
      if (mounted.current) setLoadingMore(false);
    }
  }, []);

  /** Show a run's latest state in the list (the one open beside it). */
  const update = useCallback((run: RunSummary) => {
    const fresh = summaryOf(run);
    setItems((known) =>
      known.some((item) => item.id === run.id && JSON.stringify(item) !== JSON.stringify(fresh))
        ? known.map((item) => (item.id === run.id ? fresh : item))
        : known,
    );
  }, []);

  /** Delete a finished run; true once it is gone. */
  const remove = useCallback(async (runId: number) => {
    try {
      await deleteRun(runId);
    } catch (cause) {
      if (mounted.current) setError(errorMessage(cause, 'Could not delete this run.'));
      return false;
    }
    if (mounted.current) {
      setItems((known) => known.filter((item) => item.id !== runId));
      setTotal((count) => Math.max(0, count - 1));
      setError('');
    }
    return true;
  }, []);

  return { items, total, loading, loadingMore, error, loadMore, update, remove };
}
