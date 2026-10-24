import { useState } from 'react';
import type { FormEvent, ReactNode } from 'react';

import type { Integration } from '../../core/api/types';
import { Spinner } from '../../core/ui/Spinner';
import { SpotlightCard } from '../../core/ui/reactbits/SpotlightCard';
import { actionButtonClass } from './actionButton';
import { HeaderRows } from './HeaderRows';
import {
  addressChanged,
  draftFrom,
  draftProblem,
  emptyDraft,
  toIntegrationName,
} from './integrationDraft';
import type { IntegrationDraft } from './integrationDraft';
import { fieldClass } from './ProviderCard';

interface IntegrationFormProps {
  /** The integration being edited; null adds a new one. */
  saved: Integration | null;
  busy: boolean;
  onSave: (draft: IntegrationDraft) => void;
  onCancel: () => void;
}

function Field({
  id,
  label,
  help,
  children,
}: {
  id: string;
  label: string;
  help: string;
  children: ReactNode;
}) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-xs text-slate-400">
        {label}
      </label>
      {children}
      <p id={`${id}-help`} className="mt-1 text-xs text-slate-400">
        {help}
      </p>
    </div>
  );
}

interface FieldsProps {
  idBase: string;
  draft: IntegrationDraft;
  onChange: (change: Partial<IntegrationDraft>) => void;
}

/** The server's name, which prefixes its tools, and its URL. */
function NameAndUrl({ idBase, draft, onChange }: FieldsProps) {
  const nameId = `${idBase}-name`;
  const urlId = `${idBase}-url`;
  return (
    <>
      <Field
        id={nameId}
        label="Name"
        help="Lowercase letters, numbers and _. Your agents see its tools as name_tool."
      >
        <input
          id={nameId}
          type="text"
          value={draft.name}
          placeholder="crm"
          autoComplete="off"
          spellCheck={false}
          aria-describedby={`${nameId}-help`}
          onChange={(event) => onChange({ name: toIntegrationName(event.target.value) })}
          className={`${fieldClass} font-mono`}
        />
      </Field>
      <Field id={urlId} label="Server URL" help="The MCP server address the service gave you.">
        <input
          id={urlId}
          type="url"
          inputMode="url"
          value={draft.url}
          placeholder="https://mcp.example.com/mcp"
          autoComplete="off"
          spellCheck={false}
          aria-describedby={`${urlId}-help`}
          onChange={(event) => onChange({ url: event.target.value })}
          className={fieldClass}
        />
      </Field>
    </>
  );
}

/** Add a server, or edit one: its name, URL and headers. */
export function IntegrationForm({ saved, busy, onSave, onCancel }: IntegrationFormProps) {
  const [draft, setDraft] = useState<IntegrationDraft>(() =>
    saved ? draftFrom(saved) : emptyDraft(),
  );
  const [tried, setTried] = useState(false);
  const idBase = saved ? `integration-form-${saved.id}` : 'integration-form-new';
  const problem = draftProblem(draft, saved);
  const patch = (change: Partial<IntegrationDraft>) =>
    setDraft((current) => ({ ...current, ...change }));

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setTried(true);
    if (!problem) onSave(draft);
  }

  return (
    <SpotlightCard variant="highlighted" className="p-5">
      <form onSubmit={handleSubmit} noValidate aria-labelledby={`${idBase}-title`}>
        <h3 id={`${idBase}-title`} className="mb-4 text-lg font-semibold">
          {saved ? `Edit ${saved.name}` : 'Add an integration'}
        </h3>
        <div className="space-y-4">
          <NameAndUrl idBase={idBase} draft={draft} onChange={patch} />
          <HeaderRows
            idBase={idBase}
            rows={draft.headers}
            moved={addressChanged(draft, saved)}
            onChange={(headers) => patch({ headers })}
          />
        </div>
        {tried && problem && (
          <p role="alert" className="mt-4 text-sm text-amber-300">
            {problem}
          </p>
        )}
        <div className="mt-5 flex flex-wrap gap-2">
          <button type="submit" disabled={busy} className={actionButtonClass('accent')}>
            {busy && <Spinner decorative className="size-3.5" />}
            {saved ? 'Save changes' : 'Connect'}
          </button>
          <button type="button" onClick={onCancel} className={actionButtonClass()}>
            Cancel
          </button>
        </div>
      </form>
    </SpotlightCard>
  );
}
