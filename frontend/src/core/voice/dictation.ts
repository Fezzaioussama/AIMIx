/** Dictated `text` added to what a message box already holds, after a space, cut at `maxLength`. */
export function appendDictation(current: string, text: string, maxLength?: number): string {
  const joined = current.trim() ? `${current.trimEnd()} ${text}` : text;
  return maxLength === undefined ? joined : joined.slice(0, maxLength);
}
