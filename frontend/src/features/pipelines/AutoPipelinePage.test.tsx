import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { SPOKEN } from '../../core/voice/speakingMic';
import { AutoPipelinePage } from './AutoPipelinePage';

vi.mock('../../core/voice/MicButton', () => import('../../core/voice/speakingMic'));
vi.mock('../../core/hooks/useModels', () => ({
  useModels: () => ({ models: ['muse-spark-1.3'], defaultModel: 'muse-spark-1.3', error: null }),
}));
vi.mock('../../core/hooks/useAgentTools', () => ({
  useAgentTools: () => ({ tools: [], error: null }),
}));
vi.mock('./useAutoPipeline', () => ({
  useAutoPipeline: () => ({
    generated: null,
    status: 'idle',
    errorMessage: '',
    successMessage: '',
    actions: { generate: vi.fn(), save: vi.fn() },
  }),
}));

const description = () => screen.getByPlaceholderText(/^Example: Analyze this product idea/);

describe('AutoPipelinePage dictation', () => {
  it('adds what was said to the workflow description', async () => {
    render(
      <MemoryRouter>
        <AutoPipelinePage />
      </MemoryRouter>,
    );
    await userEvent.type(description(), 'Write three posts from my specials');

    await userEvent.click(screen.getByRole('button', { name: 'Dictate your workflow' }));

    expect(description()).toHaveValue(`Write three posts from my specials ${SPOKEN}`);
  });
});
