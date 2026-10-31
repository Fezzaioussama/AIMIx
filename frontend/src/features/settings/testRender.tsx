import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { onTestFinished } from 'vitest';

import { AuthProvider } from '../../core/auth/AuthContext';
import { clearTokens, saveTokens } from '../../core/auth/tokenStorage';
import { SettingsPage } from './SettingsPage';

/** The Settings page as the app shows it: signed in, inside the router. */
export function renderSettingsPage() {
  saveTokens({ access: 'token' });
  onTestFinished(() => clearTokens());
  return render(
    <MemoryRouter initialEntries={['/settings']}>
      <AuthProvider>
        <SettingsPage />
      </AuthProvider>
    </MemoryRouter>,
  );
}
