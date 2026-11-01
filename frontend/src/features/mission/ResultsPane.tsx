import { ListChecks } from 'lucide-react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';

import { DISTANCE, DURATION, EASE_SMOOTH_OUT } from '../../core/ui/motionTokens';
import { RunReport } from '../runs/report/RunReport';
import { PaneHeader } from './PaneHeader';
import { PlannedDeliverables } from './PlannedDeliverables';
import type { Mission } from './useMission';

/** The report's note when the run did not use the team as it is now. */
const CHANGED_NOTE = 'Your team has changed since this run. Run it again to use the changes.';

/** M1: the old content fades out in 150ms, then the new rises 8px into place over 250ms. */
const ARRIVING = {
  initial: { opacity: 0, y: DISTANCE.base },
  animate: { opacity: 1, y: 0, transition: { duration: DURATION.fast, ease: EASE_SMOOTH_OUT } },
  exit: { opacity: 0, transition: { duration: DURATION.quick, ease: 'easeInOut' } },
} as const;

/** Reduced motion: a 150ms fade each way, nothing moves. */
const FADING = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: { duration: DURATION.quick } },
  exit: { opacity: 0, transition: { duration: DURATION.quick } },
} as const;

/**
 * What the mission has to show: the planned deliverables until it has run, then its
 * newest run's report. A new run takes the place of the last one (no motion on load).
 */
function ResultsBody({ mission }: { mission: Mission }) {
  const { followed, team } = mission;
  const { run } = followed;
  const swap = useReducedMotion() ? FADING : ARRIVING;
  return (
    <AnimatePresence initial={false} mode="wait">
      <motion.div key={run?.id ?? 'planned'} {...swap}>
        {run === null ? (
          <PlannedDeliverables team={team.pipeline} />
        ) : (
          <RunReport
            key={run.id}
            run={run}
            control={followed}
            level={3}
            extras={{ linkToRuns: true, note: followed.shown ? undefined : CHANGED_NOTE }}
          />
        )}
      </motion.div>
    </AnimatePresence>
  );
}

/** Said only when loading takes a moment, so a quick load does not flash it. */
function LoadingResults() {
  return (
    <motion.p
      initial={{ opacity: 0 }}
      animate={{ opacity: 1, transition: { delay: 0.4, duration: DURATION.quick } }}
      className="text-sm text-slate-400"
    >
      Loading your results…
    </motion.p>
  );
}

interface ResultsPaneProps {
  mission: Mission;
  /** A tab names the pane at every width (two columns). */
  tabbed: boolean;
  /** The team and its newest run are known: what to show is decided. */
  settled: boolean;
}

/**
 * The results pane: one reading column, centred in the pane, holding what the team will
 * hand over or, once it has run, the newest run's report. The pane scrolls, so a
 * deliverable's title row sticks to its top.
 */
export function ResultsPane({ mission, tabbed, settled }: ResultsPaneProps) {
  return (
    <>
      <PaneHeader pane="results" icon={ListChecks} tabbed={tabbed} />
      <div className="relative min-h-0 flex-1 overflow-y-auto px-4 [--sticky-top:0px] sm:px-6">
        <div className="mx-auto w-full max-w-[36rem] pt-5 pb-16 sm:pt-8">
          {settled ? <ResultsBody mission={mission} /> : <LoadingResults />}
        </div>
      </div>
    </>
  );
}
