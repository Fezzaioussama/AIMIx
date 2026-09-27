import { useEffect, useState } from 'react';

import { fetchModels } from '../api/models';

interface ModelsState {
  models: string[];
  defaultModel: string;
  error: string | null;
}

/**
 * Loads the model catalogue from the backend once. Both pipeline screens use
 * this instead of keeping their own hard-coded copy of the list (§3).
 */
export function useModels(): ModelsState {
  const [state, setState] = useState<ModelsState>({ models: [], defaultModel: '', error: null });

  useEffect(() => {
    let active = true;
    fetchModels()
      .then((response) => {
        if (!active) return;
        setState({ models: response.models, defaultModel: response.default, error: null });
      })
      .catch((cause: unknown) => {
        if (!active) return;
        const message = cause instanceof Error ? cause.message : 'Could not load models.';
        setState({ models: [], defaultModel: '', error: message });
      });
    return () => {
      active = false;
    };
  }, []);

  return state;
}
