import { LogOut } from 'lucide-react';
import { lazy, Suspense, type ComponentType, type LazyExoticComponent } from 'react';
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom';

import { RequireAuth } from './core/auth/RequireAuth';
import { useAuth } from './core/auth/AuthContext';
import { HOME_PATH } from './core/routes';
import { ActivePill } from './core/ui/ActivePill';
import { AmbientBackdrop } from './core/ui/AmbientBackdrop';
import { navIcon } from './core/ui/navIcons';
import { PageTransition } from './core/ui/PageTransition';
import { ScrollToTop } from './core/ui/ScrollToTop';
import { LoginPage } from './features/auth/LoginPage';
import { RegisterPage } from './features/auth/RegisterPage';
import { SCHEDULES_PATH } from './features/schedules/paths';

// Route-level code splitting keeps each feature out of the initial bundle until it is opened.
const LandingPage = lazy(() =>
  import('./features/landing/LandingPage').then((module) => ({ default: module.LandingPage })),
);
const MissionPage = lazy(() =>
  import('./features/mission/MissionPage').then((module) => ({ default: module.MissionPage })),
);
const ChatPage = lazy(() =>
  import('./features/chat/ChatPage').then((module) => ({ default: module.ChatPage })),
);
const PipelineBuilderPage = lazy(() =>
  import('./features/pipelines/PipelineBuilderPage').then((module) => ({
    default: module.PipelineBuilderPage,
  })),
);
const AutoPipelinePage = lazy(() =>
  import('./features/pipelines/AutoPipelinePage').then((module) => ({
    default: module.AutoPipelinePage,
  })),
);
const TemplatesPage = lazy(() =>
  import('./features/templates/TemplatesPage').then((module) => ({
    default: module.TemplatesPage,
  })),
);
const RunsPage = lazy(() =>
  import('./features/runs/RunsPage').then((module) => ({ default: module.RunsPage })),
);
const SchedulesPage = lazy(() =>
  import('./features/schedules/SchedulesPage').then((module) => ({
    default: module.SchedulesPage,
  })),
);
const FilesPage = lazy(() =>
  import('./features/files/FilesPage').then((module) => ({ default: module.FilesPage })),
);
const SettingsPage = lazy(() =>
  import('./features/settings/SettingsPage').then((module) => ({ default: module.SettingsPage })),
);

function lazyRoute(Page: LazyExoticComponent<ComponentType>) {
  return (
    <Suspense fallback={null}>
      <Page />
    </Suspense>
  );
}

// `paths` lists every route a section owns (and the routes below them), so
// Pipelines stays lit on /auto-pipeline and /runs/7.
const NAV_ITEMS = [
  { to: HOME_PATH, label: 'Missions', paths: [HOME_PATH] },
  { to: '/chat', label: 'Chat', paths: ['/chat'] },
  {
    to: '/pipeline',
    label: 'Pipelines',
    paths: ['/pipeline', '/auto-pipeline', '/templates', '/runs'],
  },
  { to: '/files', label: 'Files', paths: ['/files'] },
  { to: '/settings', label: 'Settings', paths: ['/settings'] },
] as const;

function ownsPath(paths: readonly string[], pathname: string): boolean {
  return paths.some((path) => pathname === path || pathname.startsWith(`${path}/`));
}

// On a phone each item is its icon over a small label, so five items and the logo fit a
// 390px bar (and 360px); from `sm` up it is the plain text row.
const navLinkClass = (isActive: boolean) =>
  [
    'relative isolate flex flex-col items-center gap-0.5 rounded-lg px-1.5 py-1.5 text-[10px] leading-none font-medium transition-colors sm:flex-row sm:px-4 sm:py-2 sm:text-[0.95rem] sm:leading-normal',
    isActive ? 'text-white' : 'text-slate-300 hover:text-slate-50 sm:text-slate-400',
  ].join(' ');

function AppNav() {
  const { logout } = useAuth();
  const { pathname } = useLocation();

  return (
    <nav className="fixed inset-x-0 top-0 z-50 flex h-[60px] items-center gap-2 border-b border-white/[0.06] bg-slate-950/70 px-3 backdrop-blur-xl sm:gap-8 sm:px-8">
      <img src="/logo.png" alt="AIMIx" className="h-8 w-auto sm:h-10" />
      <div className="flex gap-0.5 sm:gap-2">
        {NAV_ITEMS.map((item) => {
          const isActive = ownsPath(item.paths, pathname);
          const Icon = navIcon(item.to);
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
              <Icon aria-hidden="true" className="size-5 sm:hidden" />
              {item.label}
            </Link>
          );
        })}
      </div>
      {/* An icon on a phone; the label is its accessible name at every width. */}
      <button
        type="button"
        onClick={() => void logout()}
        aria-label="Log out"
        title="Log out"
        className="ml-auto shrink-0 rounded-lg p-2 text-sm whitespace-nowrap text-slate-400 transition-colors hover:bg-white/5 hover:text-slate-50 sm:px-3"
      >
        <LogOut aria-hidden="true" className="size-5 sm:hidden" />
        <span className="hidden sm:inline">Log out</span>
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
      <ScrollToTop />
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
      <Route path="/" element={lazyRoute(LandingPage)} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route element={<AppShell />}>
        <Route path={`${HOME_PATH}/:pipelineId?`} element={lazyRoute(MissionPage)} />
        <Route path="/chat" element={lazyRoute(ChatPage)} />
        <Route path="/pipeline" element={lazyRoute(PipelineBuilderPage)} />
        <Route path="/auto-pipeline" element={lazyRoute(AutoPipelinePage)} />
        <Route path="/templates" element={lazyRoute(TemplatesPage)} />
        <Route path="/files" element={lazyRoute(FilesPage)} />
        {/* A fixed path wins over the run id below it. */}
        <Route path={SCHEDULES_PATH} element={lazyRoute(SchedulesPage)} />
        <Route path="/runs/:runId?" element={lazyRoute(RunsPage)} />
        <Route path="/settings" element={lazyRoute(SettingsPage)} />
      </Route>
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}
