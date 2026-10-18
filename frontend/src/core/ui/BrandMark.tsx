import { GradientText } from './reactbits/GradientText';

/** The "AIMIx" wordmark in the animated brand gradient — one source for every header. */
export function BrandMark({ className = 'text-2xl' }: { className?: string }) {
  return (
    <GradientText className={`font-extrabold tracking-tight ${className}`}>AIMIx</GradientText>
  );
}
