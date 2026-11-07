import { useRef, useState } from 'react';

import type { Integration, IntegrationOAuth } from '../../core/api/types';
import { SwitchButton } from '../../core/ui/SwitchButton';
import { ToggleSwitch } from '../../core/ui/ToggleSwitch';
import { SpotlightCard } from '../../core/ui/reactbits/SpotlightCard';
import { actionButtonClass } from './actionButton';
import { ConfirmAction } from './ConfirmAction';
import { ConnectionTestResult, toolCount } from './ConnectionTestResult';
import { hostOf } from './integrationDraft';
import type { ConnectionTest } from './useIntegrations';

interface IntegrationCardProps {
  integration: Integration;
  test?: ConnectionTest;
  busy: boolean;
  onToggle: (enabled: boolean) => void;
  onToggleApproval: (required: boolean) => void;
  onEdit: () => void;
  onDelete: () => void;
  onTest: () => void;
  /** Start (or restart) the OAuth sign-in to the server, and forget it. */
  onSignIn: () => void;
  onSignOut: () => void;
}

/** What the card says of each OAuth state, and what its button does (Strategy + Registry). */
const OAUTH_WORDS: Record<IntegrationOAuth, { line: string; action: string }> = {
  '': { line: 'Not signed in: only its headers are sent.', action: 'Sign in with OAuth' },
  pending: {
    line: 'Sign-in started: finish it on the server, or start again.',
    action: 'Sign in again',
  },
  connected: {
    line: 'Signed in with OAuth: its tools use your account there.',
    action: 'Sign in again',
  },
};

type OAuthBlockProps = Pick<
  IntegrationCardProps,
  'integration' | 'busy' | 'onSignIn' | 'onSignOut'
>;

/** The OAuth sign-in: offered, started or done, with a way to sign out. */
function OAuthBlock({ integration, busy, onSignIn, onSignOut }: OAuthBlockProps) {
  const words = OAUTH_WORDS[integration.oauth];
  return (
    <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-white/10 bg-slate-950/40 px-3 py-2.5">
      <p className="text-sm text-slate-100">{words.line}</p>
      <div className="flex gap-2">
        {integration.oauth === 'connected' && (
          <button type="button" onClick={onSignOut} disabled={busy} className={actionButtonClass()}>
            Sign out
          </button>
        )}
        <button
          type="button"
          onClick={onSignIn}
          disabled={busy}
          className={actionButtonClass(integration.oauth === 'connected' ? undefined : 'accent')}
        >
          {words.action}
        </button>
      </div>
    </div>
  );
}

/** Whether a run stops for the owner's OK before this integration's tools act. */
function ApprovalSwitch({
  integration,
  busy,
  onToggleApproval,
}: Pick<IntegrationCardProps, 'integration' | 'busy' | 'onToggleApproval'>) {
  const labelId = `integration-${integration.id}-approval`;
  const hintId = `${labelId}-hint`;
  const asks = integration.require_approval;
  return (
    <div className="mt-3 flex items-start justify-between gap-3 rounded-lg border border-white/10 bg-slate-950/40 px-3 py-2.5">
      <div className="min-w-0">
        <p id={labelId} className="text-sm text-slate-100">
          Ask me before its tools act
        </p>
        <p id={hintId} className="mt-0.5 text-xs text-slate-400">
          {asks
            ? 'In a run, each action waits for your OK first. Chat cannot use its tools.'
            : 'Its tools act without asking you first, in runs and in chat.'}
        </p>
      </div>
      <SwitchButton
        checked={asks}
        disabled={busy}
        onChange={onToggleApproval}
        labelledBy={labelId}
        describedBy={hintId}
      />
    </div>
  );
}

function headerSummary(integration: Integration): string {
  const count = integration.headers.length;
  if (count === 0) return 'No headers';
  return count === 1 ? `1 header: ${integration.headers[0].name}` : `${count} headers`;
}

type CardHeadingProps = Pick<IntegrationCardProps, 'integration' | 'test' | 'busy' | 'onToggle'> & {
  headingId: string;
};

/** Name, host, the on/off switch, and what is known about it so far. */
function CardHeading({ headingId, integration, test, busy, onToggle }: CardHeadingProps) {
  const tools = test?.status === 'passed' ? toolCount(test.tools.length) : null;
  return (
    <>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 id={headingId} className="truncate font-mono text-lg font-semibold">
            {integration.name}
          </h3>
          <p className="truncate text-xs text-slate-400">{hostOf(integration.url)}</p>
        </div>
        <ToggleSwitch
          checked={integration.enabled}
          label={`Let agents use ${integration.name}`}
          disabled={busy}
          onChange={onToggle}
        />
      </div>
      <p className="mt-2 text-xs text-slate-400">
        {headerSummary(integration)}
        {tools && <span className="text-sky-300"> · {tools} found</span>}
        {!integration.enabled && ' · Off: agents do not use it'}
      </p>
    </>
  );
}

/** One of the account's MCP servers: what it is, whether agents use it, and its actions. */
export function IntegrationCard({
  integration,
  test,
  busy,
  onToggle,
  onToggleApproval,
  onEdit,
  onDelete,
  onTest,
  onSignIn,
  onSignOut,
}: IntegrationCardProps) {
  const [confirming, setConfirming] = useState(false);
  const deleteButton = useRef<HTMLButtonElement>(null);
  const headingId = `integration-${integration.id}`;

  return (
    <SpotlightCard as="section" aria-labelledby={headingId} className="p-5">
      <CardHeading
        headingId={headingId}
        integration={integration}
        test={test}
        busy={busy}
        onToggle={onToggle}
      />
      <ApprovalSwitch integration={integration} busy={busy} onToggleApproval={onToggleApproval} />
      <OAuthBlock integration={integration} busy={busy} onSignIn={onSignIn} onSignOut={onSignOut} />
      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onTest}
          disabled={test?.status === 'testing'}
          className={actionButtonClass('accent')}
        >
          Test connection
        </button>
        <button type="button" onClick={onEdit} disabled={busy} className={actionButtonClass()}>
          Edit
        </button>
        <button
          ref={deleteButton}
          type="button"
          onClick={() => setConfirming(true)}
          disabled={busy}
          className={actionButtonClass('danger')}
        >
          Delete
        </button>
      </div>
      {confirming && (
        <ConfirmAction
          question={`Delete ${integration.name}?`}
          consequence="Steps that use its tools stop working until you connect it again."
          confirmLabel={`Delete ${integration.name}`}
          keepLabel="Keep it"
          busy={busy}
          onConfirm={onDelete}
          onCancel={() => {
            setConfirming(false);
            deleteButton.current?.focus();
          }}
        />
      )}
      <ConnectionTestResult name={integration.name} test={test} />
    </SpotlightCard>
  );
}
