/** Where a workflow's results go when a run ends (GET /api/deliveries/<id>). */
export interface Delivery {
  id: number;
  pipeline_id: number;
  pipeline_name: string;
  /** The address's host; with `hint`, its last characters, never the whole address. */
  destination: string;
  hint: string;
  /** "Slack", "Discord" or "Webhook" (any other https address, sent JSON). */
  service: string;
  /** Nothing is sent until its owner confirms it. */
  confirmed: boolean;
  enabled: boolean;
  last_sent_at: string | null;
  /** Why the latest sending failed; null when it was delivered. */
  last_error: string | null;
}
