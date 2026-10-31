import { Link, useNavigate } from 'react-router-dom';

import type { Run } from '../../core/api/types';
import { BusyNotice } from '../../core/ui/BusyNotice';
import { Page, PageHeader } from '../../core/ui/Page';
import { NoticeLine } from '../settings/NoticeLine';
import { ScheduleList } from './ScheduleList';
import { useSchedules } from './useSchedules';

function EmptyState() {
  return (
    <p className="rounded-2xl border border-dashed border-white/10 p-6 text-sm text-slate-300">
      No schedules yet. Open a saved pipeline and choose{' '}
      <Link
        to="/pipeline"
        className="rounded-sm text-sky-300 underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400"
      >
        Schedule this pipeline
      </Link>{' '}
      to have it run by itself.
    </p>
  );
}

/**
 * The Schedules screen (at /schedules): every pipeline the account runs on its own, with when each runs next and how its last run went. Switch one on or
 * off, change it, run it now, or delete it.
 */
export function SchedulesPage() {
  const { schedules, status, notice, actions } = useSchedules();
  const navigate = useNavigate();

  return (
    <Page>
      <PageHeader
        title="Schedules"
        description="Pipelines that start on their own. Switch a schedule off to pause it, or run it now to see what it does. Each run it starts shows up in Runs marked as scheduled."
      />
      {/* Above the list, so an outcome (a refusal above all) is never below the fold. */}
      {notice && (
        <div className="mb-6 -mt-3">
          <NoticeLine notice={notice} />
        </div>
      )}
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
    </Page>
  );
}
