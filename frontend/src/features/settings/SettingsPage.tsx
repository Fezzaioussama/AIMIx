import type { FormEvent } from 'react';

import type { ProviderSettings } from '../../core/api/types';
import { ProviderCard } from './ProviderCard';
import { providerLabel } from './providerLabel';
import { useLLMSettings } from './useLLMSettings';
import type { Notice } from './useLLMSettings';

interface ProviderPickerProps {
  providers: ProviderSettings[];
  value: string;
  onChange: (name: string) => void;
}

function ProviderPicker({ providers, value, onChange }: ProviderPickerProps) {
  return (
    <fieldset className="mb-6">
      <legend className="mb-2 text-sm font-medium text-slate-300">Active provider</legend>
      <div className="flex flex-wrap gap-2">
        {providers.map((entry) => (
          <label
            key={entry.name}
            className={`flex cursor-pointer items-center gap-2 rounded-lg border px-4 py-2 text-sm transition-colors ${
              entry.name === value
                ? 'border-sky-400/50 bg-sky-400/15 text-sky-300'
                : 'border-white/10 text-slate-300 hover:bg-white/5'
            }`}
          >
            <input
              type="radio"
              name="provider"
              value={entry.name}
              checked={entry.name === value}
              onChange={() => onChange(entry.name)}
              className="accent-sky-400"
            />
            {providerLabel(entry.name)}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function NoticeLine({ notice }: { notice: Notice }) {
  const isError = notice.kind === 'error';
  return (
    <p
      role={isError ? 'alert' : 'status'}
      className={`text-sm ${isError ? 'text-red-400' : 'text-emerald-400'}`}
    >
      {notice.text}
    </p>
  );
}

export function SettingsPage() {
  const { settings, provider, drafts, status, notice, dirty, actions } = useLLMSettings();
  const busy = status !== 'idle';

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void actions.save();
  }

  return (
    <div className="min-h-[calc(100vh-60px)] bg-slate-900 px-4 py-10 text-slate-50">
      <div className="mx-auto max-w-3xl">
        <h1 className="text-2xl font-extrabold">Settings</h1>
        <p className="mt-2 mb-8 text-sm text-slate-400">
          Choose the provider your chat, pipelines and planner use, and save your own API keys. Keys
          are encrypted on the server and never shown again, only their last four characters.
          Anything you leave unset uses the server&apos;s backend/.env.
        </p>

        {status === 'loading' && <p className="text-sm text-slate-400">Loading settings…</p>}
        {settings && (
          <form onSubmit={handleSubmit} noValidate>
            <ProviderPicker
              providers={settings.providers}
              value={provider}
              onChange={actions.chooseProvider}
            />
            <div className="mb-6 space-y-4">
              {settings.providers.map((entry) => (
                <ProviderCard
                  key={entry.name}
                  entry={entry}
                  draft={drafts[entry.name] ?? { apiKey: '', model: entry.default_model }}
                  active={entry.name === provider}
                  busy={busy}
                  onChange={(patch) => actions.editDraft(entry.name, patch)}
                  onRemoveKey={() => void actions.removeKey(entry.name)}
                />
              ))}
            </div>
            <div className="flex items-center gap-4">
              <button
                type="submit"
                disabled={busy || !dirty}
                className="rounded-md bg-sky-500 px-5 py-2 text-sm font-semibold transition-colors hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {status === 'saving' ? 'Saving…' : 'Save settings'}
              </button>
              {notice && <NoticeLine notice={notice} />}
            </div>
          </form>
        )}
        {!settings && notice && <NoticeLine notice={notice} />}
      </div>
    </div>
  );
}
