import { useEffect, useState } from 'react';

import { fetchAgentTools } from '../api/agentTools';
import type { AgentTool } from '../api/types';

interface AgentToolsState {
  tools: AgentTool[];
  error: string | null;
}

/** Loads the native and MCP tool catalog for both pipeline editors. */
export function useAgentTools(): AgentToolsState {
  const [state, setState] = useState<AgentToolsState>({ tools: [], error: null });

  useEffect(() => {
    let active = true;
    fetchAgentTools()
      .then((tools) => {
        if (active) setState({ tools, error: null });
      })
      .catch((cause: unknown) => {
        if (!active) return;
        const error = cause instanceof Error ? cause.message : 'Could not load agent tools.';
        setState({ tools: [], error });
      });
    return () => {
      active = false;
    };
  }, []);

  return state;
}
