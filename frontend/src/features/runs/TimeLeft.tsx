import { useNow } from '../../core/hooks/useNow';
import { formatTimeLeft } from './approvalFormat';

interface TimeLeftProps {
  expiresAt: string;
  /** What happens when the time is up: "No answer counts as a decline." */
  consequence: string;
}

/** "27 min left · No answer counts as a decline.", ticking. */
export function TimeLeft({ expiresAt, consequence }: TimeLeftProps) {
  const now = useNow(true);
  return (
    <p className="mt-3 text-xs text-slate-400">
      <span className="tabular-nums">{formatTimeLeft(Date.parse(expiresAt) - now)}</span> ·{' '}
      {consequence}
    </p>
  );
}
