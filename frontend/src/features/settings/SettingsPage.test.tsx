import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { SettingsPage } from './SettingsPage';
import { SETTINGS, json } from './testData';

describe('SettingsPage', () => {
  afterEach(() => vi.restoreAllMocks());

  it('shows each provider with its key status, never the key itself', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(SETTINGS));
    render(<SettingsPage />);

    expect(await screen.findByRole('heading', { name: 'OpenRouter' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'OpenRouter' })).toBeChecked();
    expect(screen.getByText('Saved key ending in 9876')).toBeInTheDocument();
    expect(screen.getByLabelText('API key', { selector: '#api-key-openrouter' })).toHaveValue('');
    expect(screen.getByRole('button', { name: 'Remove saved key' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save settings' })).toBeDisabled();
  });

  it('warns when the chosen provider has no key', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ ...SETTINGS, provider: 'togetherai' }));
    render(<SettingsPage />);

    expect(await screen.findByText(/Model calls will fail until you add one/)).toBeInTheDocument();
  });
});
