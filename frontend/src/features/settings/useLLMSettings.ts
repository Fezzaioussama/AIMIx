import { useCallback, useEffect, useState } from 'react';

import * as settingsApi from '../../core/api/llmSettings';
import type { LLMSettings, LLMSettingsUpdate, ProviderSettings } from '../../core/api/types';

export interface ProviderDraft {
  /** A newly typed key; empty keeps whatever is saved. */
  apiKey: string;
  model: string;
}

type Drafts = Record<string, ProviderDraft>;

export interface Notice {
  kind: 'success' | 'error';
  text: string;
}

function initialModel(entry: ProviderSettings): string {
  return entry.models.includes(entry.default_model) ? entry.default_model : (entry.models[0] ?? '');
}

function draftsFrom(settings: LLMSettings): Drafts {
  return Object.fromEntries(
    settings.providers.map((entry) => [entry.name, { apiKey: '', model: initialModel(entry) }]),
  );
}

function errorText(cause: unknown, fallback: string): string {
  return cause instanceof Error ? cause.message : fallback;
}

/**
 * The PUT body: the chosen provider, plus only the providers whose form changed.
 * An untouched provider is left out, so it keeps following the server's default
 * model instead of pinning today's value.
 */
export function toUpdate(
  settings: LLMSettings,
  provider: string,
  drafts: Drafts,
): LLMSettingsUpdate {
  const providers = settings.providers.flatMap((entry) => {
    const draft = drafts[entry.name];
    const apiKey = draft?.apiKey.trim() ?? '';
    if (!draft || (!apiKey && draft.model === entry.default_model)) return [];
    return [
      { name: entry.name, default_model: draft.model, ...(apiKey ? { api_key: apiKey } : {}) },
    ];
  });
  return { provider, providers };
}

/** State and transport for the Settings screen, kept out of the component (§2). */
export function useLLMSettings() {
  const [settings, setSettings] = useState<LLMSettings | null>(null);
  const [provider, setProvider] = useState('');
  const [drafts, setDrafts] = useState<Drafts>({});
  const [status, setStatus] = useState<'loading' | 'idle' | 'saving'>('loading');
  const [notice, setNotice] = useState<Notice | null>(null);

  const adopt = useCallback((next: LLMSettings) => {
    setSettings(next);
    setProvider(next.provider);
    setDrafts(draftsFrom(next));
  }, []);

  useEffect(() => {
    let active = true;
    settingsApi
      .fetchLLMSettings()
      .then((loaded) => {
        if (active) adopt(loaded);
      })
      .catch((cause: unknown) => {
        if (active)
          setNotice({ kind: 'error', text: errorText(cause, 'Could not load settings.') });
      })
      .finally(() => {
        if (active) setStatus('idle');
      });
    return () => {
      active = false;
    };
  }, [adopt]);

  const chooseProvider = useCallback((name: string) => {
    setProvider(name);
    setNotice(null);
  }, []);

  const editDraft = useCallback((name: string, patch: Partial<ProviderDraft>) => {
    setDrafts((current) => ({ ...current, [name]: { ...current[name], ...patch } }));
    setNotice(null);
  }, []);

  const submit = useCallback(async (task: () => Promise<void>, done: string, failed: string) => {
    setStatus('saving');
    setNotice(null);
    try {
      await task();
      setNotice({ kind: 'success', text: done });
    } catch (cause) {
      setNotice({ kind: 'error', text: errorText(cause, failed) });
    } finally {
      setStatus('idle');
    }
  }, []);

  const save = useCallback(async () => {
    if (!settings) return;
    const update = toUpdate(settings, provider, drafts);
    // Adopting the response also clears the typed key: once saved, it exists
    // only encrypted on the server, which never sends it back.
    await submit(
      async () => adopt(await settingsApi.saveLLMSettings(update)),
      'Settings saved.',
      'Could not save settings.',
    );
  }, [adopt, drafts, provider, settings, submit]);

  const removeKey = useCallback(
    (name: string) =>
      submit(
        async () => {
          // Only this provider's key changes; other unsaved edits stay in the form.
          setSettings(await settingsApi.removeProviderKey(name));
          setDrafts((current) => ({ ...current, [name]: { ...current[name], apiKey: '' } }));
        },
        'Saved key removed.',
        'Could not remove the key.',
      ),
    [submit],
  );

  const dirty =
    settings !== null &&
    (provider !== settings.provider || toUpdate(settings, provider, drafts).providers.length > 0);

  return {
    settings,
    provider,
    drafts,
    status,
    notice,
    dirty,
    actions: { chooseProvider, editDraft, save, removeKey },
  };
}
