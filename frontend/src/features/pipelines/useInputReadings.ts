import { useCallback, useState } from 'react';

/** Told by an input's attach controls what they are reading ('' once nothing is). */
export type ReadingReport = (input: string, name: string) => void;

/**
 * What a run form's inputs are reading, by input, so the form waits (its Run, its Save)
 * rather than go without a document that has not arrived yet. `reading` is the name of
 * one still being read, '' when none is.
 */
export function useInputReadings() {
  const [readings, setReadings] = useState<Record<string, string>>({});
  const report: ReadingReport = useCallback((input, name) => {
    setReadings((current) => (current[input] === name ? current : { ...current, [input]: name }));
  }, []);
  const reading = Object.values(readings).find((name) => name !== '') ?? '';
  return { reading, report };
}
