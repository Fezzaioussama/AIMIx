import {
  CalendarClock,
  FolderOpen,
  History,
  LayoutTemplate,
  MessageSquare,
  Rocket,
  Settings,
  WandSparkles,
  Workflow,
} from 'lucide-react';
import { lazy, Suspense, type ComponentType, type LazyExoticComponent } from 'react';
import { Navigate, Outlet, Route, Routes } from 'react-router-dom';

import { RequireAuth } from './core/auth/RequireAuth';
import { useAuth } from './core/auth/AuthContext';
import { useAccountName } from './core/hooks/useAccountName';
import { HOME_PATH, LEGAL_LINKS, SHARED_RUN_PATH } from './core/routes';
import { AmbientBackdrop } from './core/ui/AmbientBackdrop';
import { AppFrame } from './core/ui/AppFrame';
import { PageTransition } from './core/ui/PageTransition';
import { ScrollToTop } from './core/ui/ScrollToTop';
import type { NavGroup } from './core/ui/SidebarNav';
import { ForgotPasswordPage } from './features/auth/ForgotPasswordPage';
import { LoginPage } from './features/auth/LoginPage';
import { RegisterPage } from './features/auth/RegisterPage';
import { ResetPasswordPage } from './features/auth/ResetPasswordPage';
import { useWaitingRuns } from './features/runs/useWaitingRuns';
import { OLD_SCHEDULES_PATH, SCHEDULES_PATH } from './features/schedules/paths';

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
const LegalPage = lazy(() =>
  import('./features/legal/LegalPage').then((module) => ({ default: module.LegalPage })),
);
const SharedRunPage = lazy(() =>
  import('./features/share/SharedRunPage').then((module) => ({
    default: module.SharedRunPage,
  })),
);

function lazyRoute(Page: LazyExoticComponent<ComponentType>) {
  return (
    <Suspense fallback={null}>
      <Page />
    </Suspense>
  );
}

/** The app's sections as the sidebar groups them; Runs counts the runs waiting for the person. */
function navGroups(waiting: number): NavGroup[] {
  return [
    {
      items: [
        { to: HOME_PATH, label: 'Missions', icon: Rocket },
        { to: '/chat', label: 'Chat', icon: MessageSquare },
      ],
    },
    {
      label: 'Pipelines',
      items: [
        { to: '/pipeline', label: 'Builder', icon: Workflow },
        { to: '/auto-pipeline', label: 'Auto Pipeline', icon: WandSparkles },
        { to: '/templates', label: 'Templates', icon: LayoutTemplate },
        {
          to: '/runs',
          label: 'Runs',
          icon: History,
          badge: { count: waiting, label: 'waiting for you' },
        },
        { to: SCHEDULES_PATH, label: 'Schedules', icon: CalendarClock },
      ],
    },
    {
      label: 'Workspace',
      items: [
        { to: '/files', label: 'Files', icon: FolderOpen },
        { to: '/settings', label: 'Settings', icon: Settings },
      ],
    },
  ];
}

/** Wraps the authenticated screens in the sidebar frame (inside the guard: no poll before sign-in). */
function AppShell() {
  const { logout } = useAuth();
  const waiting = useWaitingRuns();
  const name = useAccountName();
  return (
    <>
      <ScrollToTop />
      <AmbientBackdrop />
      <AppFrame groups={navGroups(waiting)} name={name} onLogout={() => void logout()}>
        <PageTransition>
          <Outlet />
        </PageTransition>
      </AppFrame>
    </>
  );
}

export function App() {
  return (
    <Routes>
      <Route path="/" element={lazyRoute(LandingPage)} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      {/* A run's report shared by link: public, read-only. */}
      <Route path={`${SHARED_RUN_PATH}/:token`} element={lazyRoute(SharedRunPage)} />
      {LEGAL_LINKS.map((link) => (
        <Route
          key={link.path}
          path={link.path}
          element={
            <Suspense fallback={null}>
              <LegalPage path={link.path} />
            </Suspense>
          }
        />
      ))}
      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route path={`${HOME_PATH}/:pipelineId?`} element={lazyRoute(MissionPage)} />
          <Route path="/chat" element={lazyRoute(ChatPage)} />
          <Route path="/pipeline" element={lazyRoute(PipelineBuilderPage)} />
          <Route path="/auto-pipeline" element={lazyRoute(AutoPipelinePage)} />
          <Route path="/templates" element={lazyRoute(TemplatesPage)} />
          <Route path="/files" element={lazyRoute(FilesPage)} />
          <Route path={SCHEDULES_PATH} element={lazyRoute(SchedulesPage)} />
          {/* A fixed path wins over the run id below it. */}
          <Route path={OLD_SCHEDULES_PATH} element={<Navigate to={SCHEDULES_PATH} replace />} />
          <Route path="/runs/:runId?" element={lazyRoute(RunsPage)} />
          <Route path="/settings/:tab?" element={lazyRoute(SettingsPage)} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}
