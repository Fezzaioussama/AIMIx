/** Settings → Memory: what the person told AIMIx to keep in mind in every chat, plan and run. */
export interface Memory {
  instructions: string;
  /** When it was last saved; null until something was. */
  updated_at: string | null;
  /** How long the instructions may be (the server's MEMORY_MAX_CHARS). */
  max_chars: number;
}
