import { AnimatePresence, motion } from 'motion/react';

import type { ProviderSettings } from '../../core/api/types';
import { SpotlightCard } from '../../core/ui/reactbits/SpotlightCard';
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

/** The Settings page's text field look, shared by its sections. */
export const fieldClass =
  'w-full rounded-lg border border-white/10 bg-slate-950/60 px-3 py-2 text-sm text-slate-100 outline-none transition-[border-color,box-shadow] focus:border-sky-400/60 focus:shadow-[0_0_0_3px_rgba(56,189,248,0.12)]';

/** "Active" tag that pops in on the provider the picker selects. */
function ActiveBadge({ shown }: { shown: boolean }) {
  return (
    <AnimatePresence>
      {shown && (
        <motion.span
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.8 }}
          className="rounded-full bg-sky-400/15 px-2.5 py-0.5 text-xs text-sky-300"
        >
          Active
        </motion.span>
      )}
    </AnimatePresence>
  );
}

function keyStatus(entry: ProviderSettings): string {
  if (entry.key_source === 'saved') return `Saved key ending in ${entry.key_hint}`;
  if (entry.key_source === 'environment') return 'Using the key the server provides';
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
    <SpotlightCard
      as="section"
      aria-labelledby={`provider-${entry.name}`}
      variant={active ? 'highlighted' : 'plain'}
      className="p-5"
    >
      <div className="mb-1 flex items-center justify-between">
        <h2 id={`provider-${entry.name}`} className="text-lg font-semibold">
          {label}
        </h2>
        <ActiveBadge shown={active} />
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
    </SpotlightCard>
  );
}
