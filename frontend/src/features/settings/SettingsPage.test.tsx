import { screen, within } from '@testing-library/react';
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

  it('shows one tab at a time, Providers first at /settings', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(byPath({ [API.llmSettings]: SETTINGS }));
    renderSettingsPage();

    const tabs = screen.getByRole('navigation', { name: 'Settings sections' });
    expect(
      within(tabs)
        .getAllByRole('link')
        .map((link) => link.textContent),
    ).toEqual(['Providers', 'Integrations', 'Usage', 'Account']);
    expect(within(tabs).getByRole('link', { name: 'Providers' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(within(tabs).getByRole('link', { name: 'Account' })).toHaveAttribute(
      'href',
      '/settings/account',
    );
    expect(await screen.findByRole('heading', { name: 'Providers' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Integrations' })).not.toBeInTheDocument();
  });

  it('opens the tab its address names', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(byPath({ [API.integrations]: [] }));
    renderSettingsPage('/settings/integrations');

    const tabs = screen.getByRole('navigation', { name: 'Settings sections' });
    expect(within(tabs).getByRole('link', { name: 'Integrations' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(await screen.findByRole('heading', { name: 'Integrations' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Providers' })).not.toBeInTheDocument();
  });

  it('sends an unknown tab to the first one', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(byPath({ [API.llmSettings]: SETTINGS }));
    renderSettingsPage('/settings/nope');

    expect(await screen.findByRole('heading', { name: 'Providers' })).toBeInTheDocument();
  });
});
