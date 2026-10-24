/**
 * Fixed, static glow behind the signed-in screens. Deliberately not animated:
 * the glass panels on top use backdrop blur, which would be recomputed every
 * frame over a moving background.
 */
export function AmbientBackdrop() {
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_18%_5%,rgba(6,182,212,0.16),transparent_30%),radial-gradient(circle_at_82%_18%,rgba(217,70,239,0.13),transparent_28%),radial-gradient(circle_at_52%_92%,rgba(79,70,229,0.12),transparent_32%)]" />
      <div className="absolute inset-0 bg-[linear-gradient(rgba(99,102,241,0.055)_1px,transparent_1px),linear-gradient(90deg,rgba(34,211,238,0.045)_1px,transparent_1px)] [mask-image:linear-gradient(to_bottom,black,transparent_88%)] bg-[size:48px_48px]" />
      <div className="absolute inset-x-[12%] top-0 h-px bg-gradient-to-r from-transparent via-cyan-300/50 to-transparent" />
    </div>
  );
}
