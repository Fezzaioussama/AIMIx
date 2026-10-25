import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';

import { sectionOf } from '../routes';

/**
 * A screen opens at its top. Routes keep the window's scroll position, so a button
 * low on one screen would otherwise open the next halfway down. Moving within a
 * screen (/runs → /runs/7) keeps the position.
 */
export function ScrollToTop() {
  const section = sectionOf(useLocation().pathname);
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [section]);
  return null;
}
