import { motion } from 'motion/react';

import type { Pipeline } from '../../core/api/types';
import { ActivePill } from '../../core/ui/ActivePill';

interface RecentPipelinesProps {
  pipelines: Pipeline[];
  activeId: number | undefined;
  onSelect: (pipeline: Pipeline) => void;
}

/** Saved pipelines in the builder sidebar; the highlight glides to the open one. */
export function RecentPipelines({ pipelines, activeId, onSelect }: RecentPipelinesProps) {
  return (
    <div className="mb-6 space-y-2">
      {pipelines.map((candidate, index) => {
        const active = candidate.id === activeId;
        return (
          <motion.button
            key={candidate.id}
            type="button"
            onClick={() => onSelect(candidate)}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.35, delay: Math.min(index, 8) * 0.04 }}
            className={`relative isolate flex w-full items-center justify-between rounded-lg border px-3 py-2 text-left text-sm transition-colors ${
              active
                ? 'border-sky-400/30 text-sky-200'
                : 'border-white/10 bg-white/[0.03] text-slate-200 hover:bg-white/[0.07]'
            }`}
          >
            {active && <ActivePill layoutId="recent-pipeline" className="bg-sky-400/10" />}
            <span className="truncate">{candidate.name}</span>
            <span className="shrink-0 pl-2 text-xs text-slate-400">
              {candidate.steps.length} steps
            </span>
          </motion.button>
        );
      })}
    </div>
  );
}
