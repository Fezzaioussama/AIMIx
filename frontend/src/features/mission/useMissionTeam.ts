import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiError } from '../../core/api/client';
import { errorMessage } from '../../core/api/errorMessage';
import { getPipeline, savePipeline } from '../../core/api/pipelines';
import type { Pipeline, PipelineStep } from '../../core/api/types';
import { useMountedRef } from '../../core/hooks/useMountedRef';

/** The name a mission is saved under when nothing else named it. */
export const DEFAULT_MISSION_NAME = 'My mission';

export type TeamStatus = 'idle' | 'loading' | 'saving';

/** A save's outcome: the stored team, or why it could not be saved. */
export type SaveResult = { pipeline: Pipeline; error: '' } | { pipeline: null; error: string };

interface TeamState {
  /** The team on screen; null until it is generated, loaded or adopted. */
  pipeline: Pipeline | null;
  /** The saved team has edits the server does not have yet. */
  dirty: boolean;
}

export interface MissionTeam extends TeamState {
  /** Never saved, or edited since it was. */
  unsaved: boolean;
  status: TeamStatus;
  /** Why the team could not be loaded or saved; empty when it could. */
  error: string;
  /** Shows a team made elsewhere: a generated plan, or a template's new pipeline. */
  adopt: (pipeline: Pipeline) => void;
  /** Swaps in an edited team, e.g. an applied revision. */
  replace: (pipeline: Pipeline) => void;
  patchStep: (order: number, patch: Partial<PipelineStep>) => void;
  removeStep: (order: number) => void;
  /** Saves when needed (never saved, or edited since); one save at a time. */
  save: () => Promise<SaveResult>;
}

function loadFailure(cause: unknown): string {
  if (cause instanceof ApiError && cause.status === 404) {
    return 'This mission was not found. It may have been deleted.';
  }
  return errorMessage(cause, 'Could not load this mission.');
}

function named(pipeline: Pipeline): Pipeline {
  return pipeline.name.trim() ? pipeline : { ...pipeline, name: DEFAULT_MISSION_NAME };
}

/** The stored team, unless it was edited while saving: those edits stay, under its id. */
function afterSave(latest: TeamState, saved: Pipeline, stored: Pipeline): TeamState {
  if (latest.pipeline === null || latest.pipeline === saved) {
    return { pipeline: stored, dirty: false };
  }
  return { pipeline: { ...latest.pipeline, id: stored.id }, dirty: true };
}

/** Loads a saved mission's team when the workspace opens on its address. */
function useTeamLoader(
  routeId: number | undefined,
  current: { readonly current: TeamState },
  commit: (next: TeamState) => void,
) {
  const [loading, setLoading] = useState(routeId !== undefined);
  const [error, setError] = useState('');

  useEffect(() => {
    // The first save only gives the open team its address: it is already here.
    if (routeId === undefined || current.current.pipeline?.id === routeId) return;
    const controller = new AbortController();
    setLoading(true);
    getPipeline(routeId, controller.signal)
      .then((loaded) => {
        if (controller.signal.aborted) return;
        commit({ pipeline: loaded, dirty: false });
        setError('');
        setLoading(false);
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        setError(loadFailure(cause));
        setLoading(false);
      });
    return () => controller.abort();
  }, [commit, current, routeId]);

  return { loading, error };
}

/** Saving, one request at a time: two first saves would create two pipelines. */
function useTeamSaver(
  current: { readonly current: TeamState },
  commit: (next: TeamState) => void,
) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const mounted = useMountedRef();
  const inFlight = useRef<Promise<SaveResult> | null>(null);

  const persist = useCallback(
    async (target: Pipeline): Promise<SaveResult> => {
      setSaving(true);
      setError('');
      try {
        const stored = await savePipeline(named(target));
        if (mounted.current) commit(afterSave(current.current, target, stored));
        return { pipeline: stored, error: '' };
      } catch (cause) {
        const message = errorMessage(cause, 'Could not save the mission.');
        if (mounted.current) setError(message);
        return { pipeline: null, error: message };
      } finally {
        if (mounted.current) setSaving(false);
      }
    },
    [commit, current, mounted],
  );

  const save = useCallback(async (): Promise<SaveResult> => {
    while (inFlight.current) await inFlight.current;
    const { pipeline, dirty } = current.current;
    if (pipeline === null) return { pipeline: null, error: 'There is no team to save yet.' };
    if (pipeline.id !== undefined && !dirty) return { pipeline, error: '' };
    const task = persist(pipeline);
    inFlight.current = task;
    try {
      return await task;
    } finally {
      if (inFlight.current === task) inFlight.current = null;
    }
  }, [current, persist]);

  return { saving, error, save };
}

/**
 * The mission's team: the pipeline on screen (loaded by id for a saved mission, or
 * the tab's draft for a new one), its edits, and saving. Kept out of the components (§2).
 */
export function useMissionTeam(routeId: number | undefined, draft: Pipeline | null): MissionTeam {
  const [state, setState] = useState<TeamState>(() => ({
    pipeline: routeId === undefined ? draft : null,
    dirty: false,
  }));
  // Async work reads the team here, so it is written together with every change.
  const current = useRef(state);
  const commit = useCallback((next: TeamState) => {
    current.current = next;
    setState(next);
  }, []);
  const loader = useTeamLoader(routeId, current, commit);
  const saver = useTeamSaver(current, commit);

  const edit = useCallback(
    (change: (pipeline: Pipeline) => Pipeline) => {
      const { pipeline } = current.current;
      if (pipeline !== null) commit({ pipeline: change(pipeline), dirty: true });
    },
    [commit],
  );
  const adopt = useCallback((pipeline: Pipeline) => commit({ pipeline, dirty: false }), [commit]);
  const replace = useCallback((pipeline: Pipeline) => commit({ pipeline, dirty: true }), [commit]);
  const patchStep = useCallback(
    (order: number, patch: Partial<PipelineStep>) =>
      edit((pipeline) => ({
        ...pipeline,
        steps: pipeline.steps.map((step) => (step.order === order ? { ...step, ...patch } : step)),
      })),
    [edit],
  );
  const removeStep = useCallback(
    (order: number) =>
      edit((pipeline) => ({
        ...pipeline,
        steps: pipeline.steps
          .filter((step) => step.order !== order)
          .map((step, index) => ({ ...step, order: index + 1 })),
      })),
    [edit],
  );

  const { pipeline, dirty } = state;
  return {
    pipeline,
    dirty,
    unsaved: pipeline !== null && (pipeline.id === undefined || dirty),
    status: loader.loading ? 'loading' : saver.saving ? 'saving' : 'idle',
    error: saver.error || loader.error,
    adopt,
    replace,
    patchStep,
    removeStep,
    save: saver.save,
  };
}
