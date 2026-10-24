/**
 * Every API path the client knows about, declared once (AGENTS.md §3).
 * Nothing else in the app may contain an '/api/...' string literal.
 */
export const API = {
  login: '/api/login',
  register: '/api/register',
  refresh: '/api/token/refresh',
  logout: '/api/token/logout',
  chat: '/api/chat',
  models: '/api/models',
  agentTools: '/api/agent-tools',
  pipelines: '/api/pipelines/',
  pipeline: (pipelineId: number) => `/api/pipelines/${pipelineId}/`,
  generatePipeline: '/api/pipelines/generate',
  runPipeline: (pipelineId: number) => `/api/pipelines/${pipelineId}/run`,
  extractDocument: '/api/documents/extract',
  files: '/api/files',
  /** One file of the user's workspace, by its '/'-separated path. */
  file: (path: string) => `/api/files/${path.split('/').map(encodeURIComponent).join('/')}`,
  llmSettings: '/api/llm-settings',
  llmSettingsKey: (provider: string) => `/api/llm-settings/keys/${encodeURIComponent(provider)}`,
} as const;
