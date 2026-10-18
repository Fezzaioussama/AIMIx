interface SpinnerProps {
  className?: string;
  /** Inside a control whose label already says it is busy: hide it from screen readers. */
  decorative?: boolean;
}

/** Shared loading spinner — Tailwind's animate-spin replaces the old keyframes. */
export function Spinner({ className = 'size-10', decorative = false }: SpinnerProps) {
  const a11y = decorative
    ? { 'aria-hidden': true as const }
    : { role: 'status', 'aria-label': 'Loading' };
  return (
    <span
      {...a11y}
      className={`inline-block animate-spin rounded-full border-2 border-white/20 border-t-sky-400 ${className}`}
    />
  );
}
