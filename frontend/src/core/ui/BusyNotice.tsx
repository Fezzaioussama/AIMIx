import type { ReactNode } from 'react';

import { ShinyText } from './reactbits/ShinyText';
import { Spinner } from './Spinner';

/** Centred spinner with a shimmering line saying what is in progress. */
export function BusyNotice({
  children,
  className = '',
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex flex-col items-center gap-3 ${className}`}>
      <Spinner />
      <ShinyText className="text-slate-400/80">{children}</ShinyText>
    </div>
  );
}
