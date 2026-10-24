import { motion } from 'motion/react';

import type { Notice } from './useSubmission';

/** A section's last outcome: saved, or why not. */
export function NoticeLine({ notice }: { notice: Notice }) {
  const isError = notice.kind === 'error';
  return (
    <motion.p
      key={notice.text}
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
      role={isError ? 'alert' : 'status'}
      className={`text-sm ${isError ? 'text-red-400' : 'text-emerald-400'}`}
    >
      {notice.text}
    </motion.p>
  );
}
