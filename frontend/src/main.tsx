import { MotionConfig } from 'motion/react';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';

import { App } from './App';
import { AuthProvider } from './core/auth/AuthContext';
import { forgetAllMissions } from './features/mission/missionStorage';
// Self-hosted, not Google Fonts: the app's Content-Security-Policy allows only its own origin.
import '@fontsource-variable/inter';
import './styles.css';

const container = document.getElementById('root');
if (!container) throw new Error('Root container #root is missing from index.html');

// reducedMotion="user": every motion animation honours the OS reduced-motion setting.
createRoot(container).render(
  <StrictMode>
    <BrowserRouter>
      {/* Mission drafts are kept per tab, not per account: they go when the account does. */}
      <AuthProvider forgetAccountData={forgetAllMissions}>
        <MotionConfig reducedMotion="user">
          <App />
        </MotionConfig>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
