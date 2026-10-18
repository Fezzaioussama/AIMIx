import { motion } from 'motion/react';
import type { FormEvent } from 'react';

import type { ProviderSettings } from '../../core/api/types';
import { ActivePill } from '../../core/ui/ActivePill';
import { GlowButton } from '../../core/ui/GlowButton';
import { AnimatedContent } from '../../core/ui/reactbits/AnimatedContent';
import { BlurText } from '../../core/ui/reactbits/BlurText';
import { ShinyText } from '../../core/ui/reactbits/ShinyText';
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

function NoticeLine({ notice }: { notice: Notice }) {
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

/** Page title and what the settings control. */
function SettingsHeader() {
  return (
    <header>
      <p className="mb-1 text-xs font-semibold tracking-widest uppercase">
        <ShinyText className="text-sky-400/80">Workspace</ShinyText>
      </p>
      <h1 className="text-3xl font-extrabold tracking-tight">
        <BlurText text="Settings" animateBy="letters" delay={40} />
      </h1>
      <p className="mt-2 mb-8 text-sm text-slate-400">
        Choose the provider your chat, pipelines and planner use, and save your own API keys. Keys
        are encrypted on the server and never shown again, only their last four characters. Anything
        you leave unset uses the server&apos;s backend/.env.
      </p>
    </header>
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
    <div className="min-h-[calc(100vh-60px)] px-4 py-10 text-slate-50">
      <div className="mx-auto max-w-3xl">
        <SettingsHeader />

        {status === 'loading' && <p className="text-sm text-slate-400">Loading settings…</p>}
        {settings && (
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
        )}
        {!settings && notice && <NoticeLine notice={notice} />}
      </div>
    </div>
  );
}
