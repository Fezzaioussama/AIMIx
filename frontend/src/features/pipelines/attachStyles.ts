/**
 * The look shared by the controls under a run input, "Attach a document" and "Add a web
 * page": side by side, they must match. At least 44px tall on a phone, for a finger.
 */
const BASE =
  'inline-flex min-h-11 items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.04] px-2.5 py-1.5 font-medium text-slate-200 transition-colors sm:min-h-0';

/** A button: "Add a web page". */
export const ATTACH_CONTROL = `${BASE} enabled:cursor-pointer enabled:hover:border-white/25 enabled:hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-sky-400 disabled:cursor-not-allowed disabled:opacity-60`;

/** The label around a hidden file input: "Attach a document", dimmed while it cannot be used. */
export function filePickerClass(usable: boolean): string {
  const state = usable
    ? 'cursor-pointer hover:border-white/25 hover:bg-white/10'
    : 'cursor-not-allowed opacity-60';
  return `${BASE} has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-sky-400 ${state}`;
}

/** A small action inside a message under the controls, e.g. "Add it anyway". */
export const INLINE_ACTION =
  'inline-flex min-h-11 items-center rounded-md font-medium text-sky-300 underline-offset-4 transition-colors enabled:hover:text-sky-200 enabled:hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 disabled:cursor-not-allowed disabled:opacity-60 sm:min-h-0';
