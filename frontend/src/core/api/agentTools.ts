import { API } from './endpoints';
import { request } from './client';
import type { AgentTool } from './types';

export function fetchAgentTools(): Promise<AgentTool[]> {
  return request<AgentTool[]>(API.agentTools);
}
