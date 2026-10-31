import { render } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { onTestFinished } from 'vitest';

import { AuthProvider } from '../../core/auth/AuthContext';
import { clearTokens, saveTokens } from '../../core/auth/tokenStorage';
import { SettingsPage } from './SettingsPage';

/** The Settings page as the app shows it: signed in, on its route, at `path` (a tab's address). */
export function renderSettingsPage(path = '/settings') {
  saveTokens({ access: 'token' });
  onTestFinished(() => clearTokens());
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <Routes>
          <Route path="/settings/:tab?" element={<SettingsPage />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}
