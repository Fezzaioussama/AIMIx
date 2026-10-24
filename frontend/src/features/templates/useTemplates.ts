import { useCallback, useEffect, useRef, useState } from 'react';

import * as templatesApi from '../../core/api/templates';
import type { MissionTemplate, Pipeline } from '../../core/api/types';

type Status = 'loading' | 'ready' | 'failed';

/** The template gallery's data and its one action, kept out of the components (§2). */
export function useTemplates() {
  const [templates, setTemplates] = useState<MissionTemplate[]>([]);
  const [status, setStatus] = useState<Status>('loading');
  const [loadError, setLoadError] = useState('');
  const [attempt, setAttempt] = useState(0);
  /** The slug of the template being turned into a pipeline, if any. */
  const [creating, setCreating] = useState<string | null>(null);
  const [createError, setCreateError] = useState('');
  const pending = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    templatesApi
      .listTemplates(controller.signal)
      .then((loaded) => {
        if (controller.signal.aborted) return;
        setTemplates(loaded);
        setStatus('ready');
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        setLoadError(cause instanceof Error ? cause.message : 'Could not load the templates.');
        setStatus('failed');
      });
    return () => controller.abort();
  }, [attempt]);

  // Leaving the page drops a pending creation's state updates (the server may
  // still finish it; the pipeline then simply appears in the builder's list).
  useEffect(() => () => pending.current?.abort(), []);

  const reload = useCallback(() => {
    setStatus('loading');
    setLoadError('');
    setAttempt((count) => count + 1);
  }, []);

  /** Resolves to the user's new pipeline, or null when it could not be created. */
  const create = useCallback(async (template: MissionTemplate): Promise<Pipeline | null> => {
    const controller = new AbortController();
    pending.current = controller;
    setCreating(template.slug);
    setCreateError('');
    try {
      return await templatesApi.createFromTemplate(template.slug, controller.signal);
    } catch (cause) {
      if (!controller.signal.aborted) {
        const detail = cause instanceof Error ? cause.message : 'Please try again.';
        setCreateError(`Could not start "${template.title}". ${detail}`);
      }
      return null;
    } finally {
      if (!controller.signal.aborted) setCreating(null);
    }
  }, []);

  return { templates, status, loadError, creating, createError, actions: { reload, create } };
}
