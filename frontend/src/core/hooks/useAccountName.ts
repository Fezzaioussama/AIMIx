import { useEffect, useState } from 'react';

import { whoAmI } from '../api/auth';

/**
 * The signed-in account's username, fetched once on mount. It is null until the answer
 * comes, and stays null when the request fails: the name is only shown, never relied on.
 * Unmounting aborts the request.
 */
export function useAccountName(): string | null {
  const [name, setName] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    whoAmI(controller.signal)
      .then((who) => {
        if (!controller.signal.aborted) setName(who.username);
      })
      .catch(() => {
        // Only a label; the sidebar works without it.
      });
    return () => controller.abort();
  }, []);

  return name;
}
