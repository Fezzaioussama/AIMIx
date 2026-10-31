import { screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import { SETTINGS, byPath } from './testData';
import { renderSettingsPage } from './testRender';

describe('SettingsPage', () => {
  afterEach(() => vi.restoreAllMocks());

  it('shows each provider with its key status, never the key itself', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(
      byPath({ [API.llmSettings]: SETTINGS, [API.integrations]: [] }),
    );
    renderSettingsPage();

    expect(await screen.findByRole('heading', { name: 'OpenRouter' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'OpenRouter' })).toBeChecked();
    expect(screen.getByText('Saved key ending in 9876')).toBeInTheDocument();
    expect(screen.getByLabelText('API key', { selector: '#api-key-openrouter' })).toHaveValue('');
    expect(screen.getByRole('button', { name: 'Remove saved key' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save settings' })).toBeDisabled();
    expect(await screen.findByRole('heading', { name: 'Integrations' })).toBeInTheDocument();
  });

  it('warns when the chosen provider has no key', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(
      byPath({
        [API.llmSettings]: { ...SETTINGS, provider: 'togetherai' },
        [API.integrations]: [],
      }),
    );
    renderSettingsPage();

    expect(await screen.findByText(/Model calls will fail until you add one/)).toBeInTheDocument();
  });
});
