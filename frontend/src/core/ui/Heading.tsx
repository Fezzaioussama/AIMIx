import type { ComponentPropsWithRef } from 'react';

export type HeadingLevel = 2 | 3 | 4 | 5 | 6;

interface HeadingProps extends ComponentPropsWithRef<'h2'> {
  level: HeadingLevel;
}

/** An h2–h6 chosen by `level`, so one component can sit at any depth of a page's outline. */
export function Heading({ level, ...props }: HeadingProps) {
  const Tag = `h${level}` as const;
  return <Tag {...props} />;
}
