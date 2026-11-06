/**
 * Which chat this browser tab has open (sessionStorage), so opening what the assistant
 * built and coming back continues it; the chats themselves live on the server. Every
 * access is wrapped: blocked or full storage only means a new chat on return.
 */

/** Versioned, so a later change of what is kept starts from a clean slate. */
const KEY = 'aimix.chat.open.v1';

export function readOpenChat(): number | null {
  try {
    const raw = window.sessionStorage.getItem(KEY);
    const id = raw === null ? Number.NaN : Number(raw);
    return Number.isInteger(id) && id > 0 ? id : null;
  } catch {
    return null;
  }
}

export function writeOpenChat(chatId: number | null): void {
  try {
    if (chatId === null) window.sessionStorage.removeItem(KEY);
    else window.sessionStorage.setItem(KEY, String(chatId));
  } catch {
    // Nothing can be kept: the chat still works for this visit.
  }
}

/**
 * Forgets which chat was open: the session ending (main.tsx). The key names no
 * account, so it goes with the session, like the missions kept in the tab.
 */
export function forgetChat(): void {
  writeOpenChat(null);
}
