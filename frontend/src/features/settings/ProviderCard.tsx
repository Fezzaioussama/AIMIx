import type { ProviderSettings } from '../../core/api/types';
import { providerLabel } from './providerLabel';
import type { ProviderDraft } from './useLLMSettings';

interface ProviderCardProps {
  entry: ProviderSettings;
  draft: ProviderDraft;
  active: boolean;
  busy: boolean;
  onChange: (patch: Partial<ProviderDraft>) => void;
  onRemoveKey: () => void;
}

const fieldClass =
  'w-full rounded-md border border-white/10 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-sky-400';

function keyStatus(entry: ProviderSettings): string {
  if (entry.key_source === 'saved') return `Saved key ending in ${entry.key_hint}`;
  if (entry.key_source === 'environment') return 'Using the server key from backend/.env';
  return 'No key saved';
}

/** One provider's API key and default model. */
export function ProviderCard({
  entry,
  draft,
  active,
  busy,
  onChange,
  onRemoveKey,
}: ProviderCardProps) {
  const label = providerLabel(entry.name);
  const keyId = `api-key-${entry.name}`;
  const modelId = `default-model-${entry.name}`;
  const missingKey = active && entry.key_source === 'none' && !draft.apiKey.trim();

  return (
    <section
      aria-labelledby={`provider-${entry.name}`}
      className={`rounded-xl border bg-slate-800/60 p-5 ${active ? 'border-sky-400/50' : 'border-white/10'}`}
    >
      <div className="mb-1 flex items-center justify-between">
        <h2 id={`provider-${entry.name}`} className="text-lg font-semibold">
          {label}
        </h2>
        {active && (
          <span className="rounded-full bg-sky-400/15 px-2.5 py-0.5 text-xs text-sky-300">
            Active
          </span>
        )}
      </div>
      <p className="mb-4 text-xs text-slate-400">{keyStatus(entry)}</p>

      <label htmlFor={keyId} className="mb-1 block text-xs text-slate-400">
        API key
      </label>
      <div className="mb-4 flex gap-2">
        {/* A password field so the key is masked; autoComplete off so the browser
            does not offer to store it as this site's login password. */}
        <input
          id={keyId}
          type="password"
          autoComplete="off"
          spellCheck={false}
          value={draft.apiKey}
          placeholder={
            entry.key_source === 'saved'
              ? 'Paste a new key to replace it'
              : `Paste your ${label} key`
          }
          onChange={(event) => onChange({ apiKey: event.target.value })}
          className={fieldClass}
        />
        {entry.key_source === 'saved' && (
          <button
            type="button"
            onClick={onRemoveKey}
            disabled={busy}
            className="shrink-0 rounded-md border border-white/10 px-3 py-2 text-xs text-slate-300 transition-colors hover:bg-white/10 disabled:opacity-60"
          >
            Remove saved key
          </button>
        )}
      </div>

      <label htmlFor={modelId} className="mb-1 block text-xs text-slate-400">
        Default model
      </label>
      <select
        id={modelId}
        value={draft.model}
        onChange={(event) => onChange({ model: event.target.value })}
        className={fieldClass}
      >
        {entry.models.map((model) => (
          <option key={model} value={model}>
            {model}
          </option>
        ))}
      </select>

      {missingKey && (
        <p className="mt-3 text-xs text-amber-300">
          This provider has no key yet. Model calls will fail until you add one.
        </p>
      )}
    </section>
  );
}
