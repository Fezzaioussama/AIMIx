import type { ReactNode } from 'react';

/** The frame of every standard screen: the same padding, width and left edge on each. */
export function Page({ children }: { children: ReactNode }) {
  return (
    <div className="px-4 py-8 text-slate-50 sm:px-8 lg:py-10">
      <div className="mx-auto w-full max-w-6xl">{children}</div>
    </div>
  );
}

interface PageHeaderProps {
  /** The screen's name, as the sidebar shows it. */
  title: string;
  description?: ReactNode;
  /** Shown under the description, e.g. a link or a usage bar. */
  children?: ReactNode;
}

/** A screen's title and what it is for, the same on every screen. */
export function PageHeader({ title, description, children }: PageHeaderProps) {
  return (
    <header className="mb-8">
      <h1 className="text-3xl font-extrabold tracking-tight">{title}</h1>
      {description && <p className="mt-2 max-w-3xl text-sm text-slate-400">{description}</p>}
      {children}
    </header>
  );
}
