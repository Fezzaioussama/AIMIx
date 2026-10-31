/**
 * Every API path the client knows about, declared once (AGENTS.md §3).
 * Nothing else in the app may contain an '/api/...' string literal.
 */
export const API = {
  login: '/api/login',
  register: '/api/register',
  refresh: '/api/token/refresh',
  logout: '/api/token/logout',
  changePassword: '/api/account/password',
  exportAccount: '/api/account/export',
  deleteAccount: '/api/account/delete',
  chat: '/api/chat',
  models: '/api/models',
  agentTools: '/api/agent-tools',
  pipelines: '/api/pipelines/',
  pipeline: (pipelineId: number) => `/api/pipelines/${pipelineId}/`,
  generatePipeline: '/api/pipelines/generate',
  revisePipeline: '/api/pipelines/revise',
  pipelineRuns: (pipelineId: number) => `/api/pipelines/${pipelineId}/runs`,
  runs: '/api/runs',
  run: (runId: number) => `/api/runs/${runId}`,
  cancelRun: (runId: number) => `/api/runs/${runId}/cancel`,
  resumeRun: (runId: number) => `/api/runs/${runId}/resume`,
  usage: '/api/usage',
  approveToolCall: (runId: number, approvalId: number) =>
    `/api/runs/${runId}/approvals/${approvalId}/approve`,
  declineToolCall: (runId: number, approvalId: number) =>
    `/api/runs/${runId}/approvals/${approvalId}/decline`,
  schedules: '/api/schedules',
  schedule: (scheduleId: number) => `/api/schedules/${scheduleId}`,
  runSchedule: (scheduleId: number) => `/api/schedules/${scheduleId}/run`,
  previewSchedule: '/api/schedules/preview',
  extractDocument: '/api/documents/extract',
  transcribeVoice: '/api/voice/transcribe',
  files: '/api/files',
  /** One file of the user's workspace, by its '/'-separated path. */
  file: (path: string) => `/api/files/${path.split('/').map(encodeURIComponent).join('/')}`,
  llmSettings: '/api/llm-settings',
  llmSettingsKey: (provider: string) => `/api/llm-settings/keys/${encodeURIComponent(provider)}`,
  templates: '/api/templates',
  createFromTemplate: (slug: string) => `/api/templates/${encodeURIComponent(slug)}/use`,
  integrations: '/api/integrations',
  integration: (integrationId: number) => `/api/integrations/${integrationId}`,
  testIntegration: (integrationId: number) => `/api/integrations/${integrationId}/test`,
} as const;
