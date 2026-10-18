import { motion } from 'motion/react';
import type { ReactNode } from 'react';
import { useLocation } from 'react-router-dom';

/**
 * Eases each screen in when the route changes. Enter-only on purpose: an exit
 * animation would briefly render the outgoing page with the new route's outlet.
 */
export function PageTransition({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  return (
    <motion.div
      key={pathname}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
    >
      {children}
    </motion.div>
  );
}
