import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { BrandMark } from '../../core/ui/BrandMark';
import { ShinyText } from '../../core/ui/reactbits/ShinyText';
import { PipelineNav } from '../pipelines/PipelineNav';
import { RunDetail } from './RunDetail';
import { RunHistoryList } from './RunHistoryList';
import { useRun } from './useRun';
import { useRunHistory } from './useRunHistory';

/** The run id in /runs/:runId, or null for the list alone. */
function parseRunId(param: string | undefined): number | null {
  const id = Number(param);
  return Number.isInteger(id) && id > 0 ? id : null;
}

/**
 * Run history at /runs: every run, newest first. /runs/:runId opens one beside
 * the list (instead of it, on a phone) to follow it live, stop, resume or delete it.
 */
export function RunsPage() {
  const runId = parseRunId(useParams().runId);
  const navigate = useNavigate();
  const history = useRunHistory();
  const live = useRun(runId);
  const [deleting, setDeleting] = useState(false);
  const { update } = history;

  // The open run is polled; keep its line in the list in step with it.
  useEffect(() => {
    if (live.run) update(live.run);
  }, [live.run, update]);

  async function handleDelete(id: number) {
    setDeleting(true);
    const deleted = await history.remove(id);
    setDeleting(false);
    if (deleted) navigate('/runs');
  }

  return (
    <div className="min-h-[calc(100vh-60px)] px-4 py-10 text-slate-50 sm:px-8">
      <div className="mx-auto max-w-7xl">
        <header className="mb-8">
          <div className="mb-3 flex items-baseline gap-3">
            <BrandMark />
            <ShinyText className="text-sm text-slate-400/70">Runs</ShinyText>
          </div>
          <PipelineNav />
          <p className="mt-3 text-sm text-slate-400">
            Every pipeline run, newest first. Open one to follow it live, stop it, resume it or
            delete it. Runs keep going when you leave the page.
          </p>
        </header>
        {history.error && (
          <p role="alert" className="mb-4 rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-300">
            {history.error}
          </p>
        )}
        <div className="grid gap-8 lg:grid-cols-[320px_minmax(0,1fr)]">
          <div
            className={`${runId === null ? '' : 'hidden lg:block'} lg:sticky lg:top-[84px] lg:max-h-[calc(100vh-108px)] lg:self-start lg:overflow-y-auto`}
          >
            <RunHistoryList
              items={history.items}
              total={history.total}
              selectedId={runId}
              loading={history.loading}
              loadingMore={history.loadingMore}
              onLoadMore={() => void history.loadMore()}
            />
          </div>
          <div className={runId === null ? 'hidden lg:block' : 'min-w-0'}>
            {runId === null ? (
              <p className="rounded-2xl border border-dashed border-white/10 p-8 text-center text-sm text-slate-400">
                Choose a run to see its steps and results.
              </p>
            ) : (
              <>
                <Link
                  to="/runs"
                  className="mb-4 inline-block text-sm text-sky-300 underline-offset-2 hover:underline lg:hidden"
                >
                  ← All runs
                </Link>
                <RunDetail
                  live={live}
                  onDelete={() => void handleDelete(runId)}
                  deleting={deleting}
                />
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
