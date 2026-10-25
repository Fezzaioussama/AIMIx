import type { ReactNode } from 'react';
import { Link, useMatch } from 'react-router-dom';

import { BrandMark } from '../../core/ui/BrandMark';
import { ShinyText } from '../../core/ui/reactbits/ShinyText';
import { PipelineNav } from '../pipelines/PipelineNav';
import { SCHEDULES_PATH } from '../schedules/paths';

const TAB_CLASS = (active: boolean) =>
  [
    '-mb-px border-b-2 px-1 pt-1 pb-2 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400',
    active
      ? 'border-sky-400 text-sky-200'
      : 'border-transparent text-slate-400 hover:text-slate-50',
  ].join(' ');

/** The Runs screen's two views: every run, and the schedules that start some of them. */
function RunsTabs() {
  const onSchedules = useMatch(SCHEDULES_PATH) !== null;
  return (
    <nav aria-label="Runs views" className="mt-4 flex gap-6 border-b border-white/10">
      <Link
        to="/runs"
        aria-current={onSchedules ? undefined : 'page'}
        className={TAB_CLASS(!onSchedules)}
      >
        History
      </Link>
      <Link
        to={SCHEDULES_PATH}
        aria-current={onSchedules ? 'page' : undefined}
        className={TAB_CLASS(onSchedules)}
      >
        Schedules
      </Link>
    </nav>
  );
}

/** The header both Runs views share: the brand, the pipeline sub-navigation, the two views. */
export function RunsHeader({ children }: { children: ReactNode }) {
  return (
    <header className="mb-8">
      <div className="mb-3 flex items-baseline gap-3">
        <BrandMark />
        <ShinyText className="text-sm text-slate-400/70">Runs</ShinyText>
      </div>
      <PipelineNav />
      <RunsTabs />
      <p className="mt-3 text-sm text-slate-400">{children}</p>
    </header>
  );
}
