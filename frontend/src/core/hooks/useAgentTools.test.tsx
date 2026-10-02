import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from '../api/endpoints';
import { useAgentTools } from './useAgentTools';

describe('useAgentTools', () => {
  afterEach(() => vi.restoreAllMocks());

  it('reports catalog failures without granting an invented tool selection', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ error: 'tool_discovery_failed', detail: 'MCP is unavailable' }),
        {
          status: 503,
          headers: { 'Content-Type': 'application/json' },
        },
      ),
    );

    const { result } = renderHook(() => useAgentTools());
    await waitFor(() => expect(result.current.error).toBe('MCP is unavailable'));
    expect(result.current.tools).toEqual([]);
    expect(fetchMock.mock.calls[0][0]).toBe(API.agentTools);
  });
});
