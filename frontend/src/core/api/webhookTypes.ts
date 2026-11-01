/** A webhook as its owner reads it (GET /api/webhooks/<id>): the secret token of its link. */
export interface WebhookLink {
  id: number;
  pipeline_id: number;
  pipeline_name: string;
  enabled: boolean;
  last_called_at: string | null;
  /** Why its latest call started no run; null when it started one. */
  last_error: string | null;
  token: string;
}
