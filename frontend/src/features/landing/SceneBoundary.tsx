import { Component } from 'react';
import type { ReactNode } from 'react';

interface SceneBoundaryProps {
  children: ReactNode;
  /** Shown instead of the scene if it throws (e.g. the GPU refuses a context). */
  fallback: ReactNode;
}

/**
 * Keeps a failing decorative effect from taking the page down with it: the hero
 * simply falls back to its flat version. Error boundaries must be classes.
 */
export class SceneBoundary extends Component<SceneBoundaryProps, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error) {
    console.warn('The hero scene could not start; showing the flat version.', error.message);
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}
