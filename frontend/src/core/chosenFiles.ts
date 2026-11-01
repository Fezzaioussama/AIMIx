import type { ChangeEvent } from 'react';

/**
 * The files a file input was just given. The input is emptied, so choosing the same file
 * again still counts as a change.
 */
export function chosenFiles(event: ChangeEvent<HTMLInputElement>): File[] {
  const files = [...(event.target.files ?? [])];
  event.target.value = '';
  return files;
}
