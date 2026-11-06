import type { Usage } from '../../core/api/types';
import type { ChatMessage } from './useChatStream';

const NOTHING: Usage = { input_tokens: 0, output_tokens: 0, cost_usd: null, cost_complete: true };

/** What every reply of a chat used in all: the known costs added up, complete when all are. */
export function totalUsage(messages: ChatMessage[]): Usage {
  return messages.reduce<Usage>((sum, message) => {
    const usage = message.usage;
    if (!usage) return sum;
    const cost =
      sum.cost_usd === null && usage.cost_usd === null
        ? null
        : (sum.cost_usd ?? 0) + (usage.cost_usd ?? 0);
    return {
      input_tokens: sum.input_tokens + usage.input_tokens,
      output_tokens: sum.output_tokens + usage.output_tokens,
      cost_usd: cost,
      cost_complete: sum.cost_complete && usage.cost_complete,
    };
  }, NOTHING);
}
