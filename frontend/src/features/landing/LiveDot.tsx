const TONES = { emerald: 'bg-emerald-400', sky: 'bg-sky-400' } as const;

/** A status dot with a soft expanding ring (still under reduced motion). */
export function LiveDot({ tone = 'emerald' }: { tone?: keyof typeof TONES }) {
  const color = TONES[tone];
  return (
    <span aria-hidden="true" className="relative flex size-2 shrink-0">
      <span
        className={`absolute inline-flex size-full rounded-full motion-safe:animate-ping-soft ${color}`}
      />
      <span className={`relative inline-flex size-2 rounded-full ${color}`} />
    </span>
  );
}
