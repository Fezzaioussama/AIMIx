import type { FormEvent } from 'react';

import type { ProviderSettings } from '../../core/api/types';
import { ActivePill } from '../../core/ui/ActivePill';
import { GlowButton } from '../../core/ui/GlowButton';
import { AnimatedContent } from '../../core/ui/reactbits/AnimatedContent';
import { NoticeLine } from './NoticeLine';
import { ProviderCard } from './ProviderCard';
import { providerLabel } from './providerLabel';
import { useLLMSettings } from './useLLMSettings';

interface ProviderPickerProps {
  providers: ProviderSettings[];
  value: string;
  onChange: (name: string) => void;
}

function ProviderPicker({ providers, value, onChange }: ProviderPickerProps) {
  return (
    <fieldset className="mb-6">
      <legend className="mb-2 text-sm font-medium text-slate-300">Active provider</legend>
      <div className="inline-flex flex-wrap gap-1 rounded-xl border border-white/10 bg-slate-900/60 p-1">
        {providers.map((entry) => (
          <label
            key={entry.name}
            className={`relative isolate flex cursor-pointer items-center rounded-lg px-4 py-2 text-sm transition-colors has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-sky-400 ${
              entry.name === value ? 'text-white' : 'text-slate-400 hover:text-slate-100'
            }`}
          >
            {entry.name === value && (
              <ActivePill
                layoutId="provider-picker"
                className="bg-gradient-to-r from-sky-500/80 to-indigo-500/80 shadow-[0_6px_20px_-8px_rgba(99,102,241,0.8)]"
              />
            )}
            {/* The native radio stays for keyboard and screen-reader users; the pill draws it. */}
            <input
              type="radio"
              name="provider"
              value={entry.name}
              checked={entry.name === value}
              onChange={() => onChange(entry.name)}
              className="sr-only"
            />
            {providerLabel(entry.name)}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

/** The active provider, a card per provider with its key and model, and Save. */
function ProvidersForm({ llm }: { llm: ReturnType<typeof useLLMSettings> }) {
  const { settings, provider, drafts, status, notice, dirty, actions } = llm;
  const busy = status !== 'idle';

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void actions.save();
  }

  if (!settings) return null;
  return (
    <form onSubmit={handleSubmit} noValidate>
      <ProviderPicker
        providers={settings.providers}
        value={provider}
        onChange={actions.chooseProvider}
      />
      <div className="mb-6 space-y-4">
        {settings.providers.map((entry, index) => (
          <AnimatedContent key={entry.name} distance={18} delay={index * 0.07}>
            <ProviderCard
              entry={entry}
              draft={drafts[entry.name] ?? { apiKey: '', model: entry.default_model }}
              active={entry.name === provider}
              busy={busy}
              onChange={(patch) => actions.editDraft(entry.name, patch)}
              onRemoveKey={() => void actions.removeKey(entry.name)}
            />
          </AnimatedContent>
        ))}
      </div>
      <div className="flex items-center gap-4">
        <GlowButton type="submit" disabled={busy || !dirty} busy={status === 'saving'}>
          {status === 'saving' ? 'Saving…' : 'Save settings'}
        </GlowButton>
        {notice && <NoticeLine notice={notice} />}
      </div>
    </form>
  );
}

/** The Providers tab of Settings: which provider the app uses, and the keys saved for each. */
export function ProvidersSection() {
  const llm = useLLMSettings();
  return (
    <section aria-labelledby="providers-heading" className="mt-8">
      <h2 id="providers-heading" className="text-2xl font-bold tracking-tight">
        Providers
      </h2>
      <p className="mt-2 mb-6 text-sm text-slate-400">
        Choose the provider your chat, pipelines and planner use, and save your own API keys. Keys
        are encrypted on the server and never shown again, only their last four characters. Anything
        you leave unset uses the key the server provides, when it has one.
      </p>
      {llm.status === 'loading' && <p className="text-sm text-slate-400">Loading settings…</p>}
      <ProvidersForm llm={llm} />
      {!llm.settings && llm.notice && <NoticeLine notice={llm.notice} />}
    </section>
  );
}
