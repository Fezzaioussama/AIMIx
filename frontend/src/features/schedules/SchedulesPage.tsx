import { Link, useNavigate } from 'react-router-dom';

import type { Run } from '../../core/api/types';
import { BusyNotice } from '../../core/ui/BusyNotice';
import { RunsHeader } from '../runs/RunsHeader';
import { NoticeLine } from '../settings/NoticeLine';
import { ScheduleList } from './ScheduleList';
import { useSchedules } from './useSchedules';

function EmptyState() {
  return (
    <p className="rounded-2xl border border-dashed border-white/10 p-6 text-sm text-slate-300">
      No schedules yet. Open a saved pipeline and choose{' '}
      <Link to="/pipeline" className="text-sky-300 underline-offset-2 hover:underline">
        Schedule this pipeline
      </Link>{' '}
      to have it run by itself.
    </p>
  );
}

/**
 * The Schedules view of the Runs screen (at /runs/schedules): every pipeline the account
 * runs on its own, with when each runs next and how its last run went. Switch one on or
 * off, change it, run it now, or delete it.
 */
export function SchedulesPage() {
  const { schedules, status, notice, actions } = useSchedules();
  const navigate = useNavigate();

  return (
    <div className="min-h-[calc(100vh-60px)] px-4 py-10 text-slate-50 sm:px-8">
      <div className="mx-auto max-w-7xl">
        <RunsHeader>
          Pipelines that start on their own. Switch a schedule off to pause it, or run it now to see
          what it does. Each run it starts shows up in History marked as scheduled.
        </RunsHeader>
        {status === 'loading' && <BusyNotice className="mt-12">Loading your schedules…</BusyNotice>}
        {schedules?.length === 0 && <EmptyState />}
        {schedules && schedules.length > 0 && (
          <ScheduleList
            schedules={schedules}
            busy={status !== 'idle'}
            actions={actions}
            onStarted={(run: Run) => navigate(`/runs/${run.id}`)}
          />
        )}
        {notice && (
          <div className="mt-4">
            <NoticeLine notice={notice} />
          </div>
        )}
      </div>
    </div>
  );
}
