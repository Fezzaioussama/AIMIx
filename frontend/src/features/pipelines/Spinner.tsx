/** Shared loading spinner — Tailwind's animate-spin replaces the old keyframes. */
export function Spinner({ className = 'size-10' }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={`inline-block animate-spin rounded-full border-2 border-white/20 border-t-sky-400 ${className}`}
    />
  );
}
