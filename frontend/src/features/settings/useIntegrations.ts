import { useCallback, useEffect, useRef, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';

import * as integrationsApi from '../../core/api/integrations';
import type { Integration, IntegrationTool } from '../../core/api/types';
import { toCreate, toPatch } from './integrationDraft';
import type { IntegrationDraft } from './integrationDraft';
import { errorText, useSubmission } from './useSubmission';
import type { Submission } from './useSubmission';

/** The last connection test of one integration, kept while the page is open. */
export type ConnectionTest =
  | { status: 'testing' }
  | { status: 'passed'; tools: IntegrationTool[] }
  | { status: 'failed'; error: string };

/** Which form is open: none, a new integration, or the edit of one (its id). */
export type Editing = null | 'new' | number;

type IntegrationList = Integration[] | null;

function without<T>(record: Record<number, T>, id: number): Record<number, T> {
  const rest = { ...record };
  delete rest[id];
  return rest;
}

/** The account's integrations, loaded once; a failure goes to the section's notice. */
function useIntegrationList({ setNotice, setStatus }: Submission) {
  const [integrations, setIntegrations] = useState<IntegrationList>(null);

  useEffect(() => {
    let active = true;
    integrationsApi
      .listIntegrations()
      .then((loaded) => {
        if (active) setIntegrations(loaded);
      })
      .catch((cause: unknown) => {
        if (active)
          setNotice({ kind: 'error', text: errorText(cause, 'Could not load your integrations.') });
      })
      .finally(() => {
        if (active) setStatus('idle');
      });
    return () => {
      active = false;
    };
  }, [setNotice, setStatus]);

  return [integrations, setIntegrations] as const;
}

/** The last test of each integration; tests still running are cancelled on unmount. */
function useConnectionTests() {
  const [tests, setTests] = useState<Record<number, ConnectionTest>>({});
  const pending = useRef(new Set<AbortController>());

  useEffect(() => {
    const running = pending.current;
    return () => running.forEach((controller) => controller.abort());
  }, []);

  const forget = useCallback((id: number) => setTests((current) => without(current, id)), []);

  const test = useCallback(async (integration: Integration) => {
    const controller = new AbortController();
    pending.current.add(controller);
    const record = (result: ConnectionTest) => {
      if (!controller.signal.aborted)
        setTests((current) => ({ ...current, [integration.id]: result }));
    };
    record({ status: 'testing' });
    try {
      const { tools } = await integrationsApi.testIntegration(integration.id, controller.signal);
      record({ status: 'passed', tools });
    } catch (cause) {
      record({ status: 'failed', error: errorText(cause, 'The connection test failed.') });
    } finally {
      pending.current.delete(controller);
    }
  }, []);

  return { tests, test, forget };
}

interface MutationContext {
  submit: Submission['submit'];
  setIntegrations: Dispatch<SetStateAction<IntegrationList>>;
  setEditing: Dispatch<SetStateAction<Editing>>;
  /** Drops an integration's test result, which a change may have made stale. */
  forget: (id: number) => void;
}

const SAVE_FAILED = 'Could not save the integration.';

/** Create, edit, switch on or off, and delete; each says how it went. */
function mutations({ submit, setIntegrations, setEditing, forget }: MutationContext) {
  const replace = (saved: Integration) =>
    setIntegrations((current) =>
      (current ?? []).map((item) => (item.id === saved.id ? saved : item)),
    );
  return {
    create: (draft: IntegrationDraft) =>
      submit(
        async () => {
          const saved = await integrationsApi.createIntegration(toCreate(draft));
          setIntegrations((current) => [...(current ?? []), saved]);
          setEditing(null);
        },
        `${draft.name} is connected. Test it to see its tools.`,
        SAVE_FAILED,
      ),
    update: (saved: Integration, draft: IntegrationDraft) =>
      submit(
        async () => {
          replace(await integrationsApi.updateIntegration(saved.id, toPatch(draft, saved)));
          forget(saved.id);
          setEditing(null);
        },
        'Integration saved.',
        SAVE_FAILED,
      ),
    setEnabled: (integration: Integration, enabled: boolean) =>
      submit(
        async () => replace(await integrationsApi.updateIntegration(integration.id, { enabled })),
        enabled
          ? `${integration.name} is on: your agents can use its tools.`
          : `${integration.name} is off: your agents will not use it.`,
        'Could not change the integration.',
      ),
    remove: (integration: Integration) =>
      submit(
        async () => {
          await integrationsApi.deleteIntegration(integration.id);
          setIntegrations((current) =>
            (current ?? []).filter((item) => item.id !== integration.id),
          );
          forget(integration.id);
          setEditing((current) => (current === integration.id ? null : current));
        },
        `${integration.name} is deleted.`,
        'Could not delete the integration.',
      ),
  };
}

/** State and transport for Settings → Integrations, kept out of the components (§2). */
export function useIntegrations() {
  const submission = useSubmission('loading');
  const { status, notice, setNotice, submit } = submission;
  const [integrations, setIntegrations] = useIntegrationList(submission);
  const { tests, test, forget } = useConnectionTests();
  const [editing, setEditing] = useState<Editing>(null);

  const startEditing = (next: Editing) => {
    setEditing(next);
    setNotice(null);
  };

  return {
    integrations,
    tests,
    editing,
    status,
    notice,
    actions: {
      startEditing,
      test,
      ...mutations({ submit, setIntegrations, setEditing, forget }),
    },
  };
}
