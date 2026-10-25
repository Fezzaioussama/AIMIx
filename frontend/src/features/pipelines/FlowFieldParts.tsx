import type { ReactNode } from 'react';

/** What is wrong with a flow field, in amber under it; nothing while there is no problem. */
export function Problem({ id, text }: { id: string; text: string | null }) {
  if (text === null) return null;
  return (
    <p id={id} className="text-[11px] text-amber-300">
      {text}
    </p>
  );
}

/** A flow field with its visible label. */
export function Labelled({
  id,
  label,
  children,
}: {
  id: string;
  label: string;
  children: ReactNode;
}) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-slate-400">
        {label}
      </label>
      {children}
    </div>
  );
}
