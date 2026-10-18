/**
 * Fixed, static glow behind the signed-in screens. Deliberately not animated:
 * the glass panels on top use backdrop blur, which would be recomputed every
 * frame over a moving background.
 */
export function AmbientBackdrop() {
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <div className="absolute -top-40 -left-32 size-[34rem] rounded-full bg-sky-500/15 blur-3xl" />
      <div className="absolute -top-24 right-[-10rem] size-[30rem] rounded-full bg-purple-600/15 blur-3xl" />
      <div className="absolute bottom-[-14rem] left-1/3 size-[36rem] rounded-full bg-indigo-600/10 blur-3xl" />
      <div className="absolute inset-0 bg-[radial-gradient(rgba(148,163,184,0.07)_1px,transparent_1px)] [mask-image:linear-gradient(to_bottom,black,transparent_85%)] bg-[size:22px_22px]" />
    </div>
  );
}
