import { Check, Copy } from 'lucide-react';

import { sharedRunUrl } from '../../core/api/runs';
import { useCopyToClipboard } from '../../core/hooks/useCopyToClipboard';
import { RUN_BUTTON } from './runButtons';
import { useRunShare } from './useRunShare';

/**
 * "Share": a secret link to the run's report, read by anyone who has it without an
 * account, then the link with Copy link and Stop sharing. Offered once the run has
 * ended; the link is read again each time the run opens.
 */
export function ShareRunButton({ runId }: { runId: number }) {
  const { link, busy, error, share, unshare } = useRunShare(runId);
  const { status, copy } = useCopyToClipboard();
  if (link === undefined) return null;
  const failure = error && (
    <span role="alert" className="basis-full text-sm text-amber-300">
      {error}
    </span>
  );
  if (link === null) {
    return (
      <>
        <button
          type="button"
          onClick={() => void share()}
          disabled={busy}
          className={RUN_BUTTON.neutral}
        >
          {busy ? 'Sharing…' : 'Share'}
        </button>
        {failure}
      </>
    );
  }
  const url = sharedRunUrl(link.token);
  const copied = status === 'copied';
  return (
    <span
      role="group"
      aria-label="Share link"
      className="flex min-w-0 flex-wrap items-center gap-2"
    >
      <code
        title={url}
        className="max-w-[16rem] truncate rounded bg-slate-950/60 px-2 py-1 font-mono text-xs text-slate-200"
      >
        {url}
      </code>
      <button type="button" onClick={() => void copy(url)} className={RUN_BUTTON.neutral}>
        {copied ? (
          <Check aria-hidden="true" className="size-4" />
        ) : (
          <Copy aria-hidden="true" className="size-4" />
        )}
        {copied ? 'Copied' : 'Copy link'}
      </button>
      <button
        type="button"
        onClick={() => void unshare()}
        disabled={busy}
        className={RUN_BUTTON.neutral}
      >
        {busy ? 'Stopping…' : 'Stop sharing'}
      </button>
      <span className="basis-full text-xs text-slate-400">
        Anyone with the link can read this report, without an account.
      </span>
      {failure}
    </span>
  );
}
