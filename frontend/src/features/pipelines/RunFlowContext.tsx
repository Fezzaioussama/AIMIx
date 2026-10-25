import { createContext, useContext } from 'react';

import type { PipelineInput, PipelineStep } from '../../core/api/types';

/**
 * The pipeline a followed run executed (its own snapshot). The cards of its steps read
 * what they need from it, such as a skipped step's condition or how many rounds a review
 * loop allows, instead of every level passing it down.
 */
export interface RunFlow {
  steps: PipelineStep[];
  inputs: PipelineInput[];
}

export const NO_FLOW: RunFlow = { steps: [], inputs: [] };

export const RunFlowContext = createContext<RunFlow>(NO_FLOW);

export function useRunFlow(): RunFlow {
  return useContext(RunFlowContext);
}
