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
  llmSettings: '/api/llm-settings',
  llmSettingsKey: (provider: string) => `/api/llm-settings/keys/${encodeURIComponent(provider)}`,
  templates: '/api/templates',
  createFromTemplate: (slug: string) => `/api/templates/${encodeURIComponent(slug)}/use`,
} as const;
