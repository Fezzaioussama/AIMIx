import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom';

import { RequireAuth } from './core/auth/RequireAuth';
import { useAuth } from './core/auth/AuthContext';
import { ActivePill } from './core/ui/ActivePill';
import { AmbientBackdrop } from './core/ui/AmbientBackdrop';
import { PageTransition } from './core/ui/PageTransition';
import { LoginPage } from './features/auth/LoginPage';
import { RegisterPage } from './features/auth/RegisterPage';
import { ChatPage } from './features/chat/ChatPage';
import { AutoPipelinePage } from './features/pipelines/AutoPipelinePage';
import { PipelineBuilderPage } from './features/pipelines/PipelineBuilderPage';
import { SettingsPage } from './features/settings/SettingsPage';

// `paths` lists every route a section owns, so Pipelines stays lit on /auto-pipeline.
const NAV_ITEMS = [
  { to: '/chat', label: 'Chat', paths: ['/chat'] },
  { to: '/pipeline', label: 'Pipelines', paths: ['/pipeline', '/auto-pipeline'] },
  { to: '/settings', label: 'Settings', paths: ['/settings'] },
] as const;

const navLinkClass = (isActive: boolean) =>
  [
    'relative isolate rounded-lg px-2.5 py-2 text-[0.95rem] font-medium transition-colors sm:px-4',
    isActive ? 'text-white' : 'text-slate-400 hover:text-slate-50',
  ].join(' ');

function AppNav() {
  const { logout } = useAuth();
  const { pathname } = useLocation();

  return (
    <nav className="fixed inset-x-0 top-0 z-50 flex h-[60px] items-center gap-3 border-b border-white/[0.06] bg-slate-950/70 px-4 backdrop-blur-xl sm:gap-8 sm:px-8">
      <img src="/logo.png" alt="AIMIx" className="h-8 w-auto sm:h-10" />
      <div className="flex gap-1 sm:gap-2">
        {NAV_ITEMS.map((item) => {
          const isActive = (item.paths as readonly string[]).includes(pathname);
          return (
            <Link
              key={item.to}
              to={item.to}
              aria-current={isActive ? 'page' : undefined}
              className={navLinkClass(isActive)}
            >
              {isActive && (
                <ActivePill
                  layoutId="app-nav"
                  className="bg-white/[0.08] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)]"
                />
              )}
              {item.label}
            </Link>
          );
        })}
      </div>
      <button
        type="button"
        onClick={logout}
        className="ml-auto shrink-0 rounded-lg px-2 py-2 text-sm whitespace-nowrap text-slate-400 transition-colors hover:bg-white/5 hover:text-slate-50 sm:px-3"
      >
        Log out
      </button>
      {/* Hairline in the brand gradient along the bottom edge. */}
      <span
        aria-hidden="true"
        className="absolute inset-x-0 -bottom-px h-px bg-gradient-to-r from-transparent via-indigo-400/50 to-transparent"
      />
    </nav>
  );
}

/** Wraps the authenticated screens with the fixed nav and its 60px offset. */
function AppShell() {
  return (
    <>
      <AmbientBackdrop />
      <AppNav />
      <div className="pt-[60px]">
        <PageTransition>
          <RequireAuth />
        </PageTransition>
      </div>
    </>
  );
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route element={<AppShell />}>
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/pipeline" element={<PipelineBuilderPage />} />
        <Route path="/auto-pipeline" element={<AutoPipelinePage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}
