import { NavLink, Navigate, Route, Routes } from 'react-router-dom';

import { RequireAuth } from './core/auth/RequireAuth';
import { useAuth } from './core/auth/AuthContext';
import { LoginPage } from './features/auth/LoginPage';
import { RegisterPage } from './features/auth/RegisterPage';
import { ChatPage } from './features/chat/ChatPage';
import { AutoPipelinePage } from './features/pipelines/AutoPipelinePage';
import { PipelineBuilderPage } from './features/pipelines/PipelineBuilderPage';

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  [
    'rounded-lg px-4 py-2 text-[0.95rem] font-medium transition-colors',
    isActive ? 'bg-sky-400/10 text-sky-400' : 'text-slate-400 hover:bg-white/5 hover:text-slate-50',
  ].join(' ');

function AppNav() {
  const { logout } = useAuth();

  return (
    <nav className="fixed inset-x-0 top-0 z-50 flex h-[60px] items-center gap-8 border-b border-white/10 bg-slate-900/80 px-8 backdrop-blur-md">
      <img src="/logo.png" alt="AIMIx" className="h-10 w-auto" />
      <div className="flex gap-8">
        <NavLink to="/chat" className={navLinkClass}>
          Chat
        </NavLink>
        <NavLink to="/pipeline" className={navLinkClass}>
          Pipelines
        </NavLink>
      </div>
      <button
        type="button"
        onClick={logout}
        className="ml-auto rounded-lg px-3 py-2 text-sm text-slate-400 transition-colors hover:bg-white/5 hover:text-slate-50"
      >
        Log out
      </button>
    </nav>
  );
}

/** Wraps the authenticated screens with the fixed nav and its 60px offset. */
function AppShell() {
  return (
    <>
      <AppNav />
      <div className="pt-[60px]">
        <RequireAuth />
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
      </Route>
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}
