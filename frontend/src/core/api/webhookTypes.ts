/** A webhook as its owner sees it in a list (GET /api/webhooks): never its token. */
export interface Webhook {
  id: number;
  pipeline_id: number;
  pipeline_name: string;
  enabled: boolean;
  last_called_at: string | null;
  /** Why its latest call started no run; null when it started one. */
  last_error: string | null;
}

/** One webhook with the secret token of its link (GET /api/webhooks/<id>), for its owner. */
export interface WebhookLink extends Webhook {
  token: string;
}
