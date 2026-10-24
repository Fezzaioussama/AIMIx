import { useAuth } from '../../core/auth/AuthContext';

export interface Cta {
  label: string;
  to: string;
}

export interface LandingCtas {
  primary: Cta;
  secondary: Cta;
}

const VISITOR: LandingCtas = {
  primary: { label: 'Get started', to: '/register' },
  secondary: { label: 'Sign in', to: '/login' },
};

const MEMBER: LandingCtas = {
  primary: { label: 'Open the app', to: '/chat' },
  secondary: { label: 'Build a pipeline', to: '/pipeline' },
};

/** The page's two calls to action, switched once so every section agrees on them. */
export function useLandingCtas(): LandingCtas {
  return useAuth().isAuthenticated ? MEMBER : VISITOR;
}
