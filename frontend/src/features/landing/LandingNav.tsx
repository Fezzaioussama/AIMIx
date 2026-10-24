import { AnimatePresence, motion, useMotionValueEvent, useScroll } from 'motion/react';
import { Menu, X } from 'lucide-react';
import { useState } from 'react';
import type { KeyboardEvent } from 'react';
import { Link } from 'react-router-dom';

import { glowButtonClass } from '../../core/ui/GlowButton';
import { NAV_LINKS, RELEASE_STAGE } from './content/site';
import { GhostLink } from './GhostLink';
import { useLandingCtas } from './useLandingCtas';

const LINK =
  'rounded-lg px-3 py-2 text-sm font-medium text-slate-300 transition-colors hover:text-white focus-visible:outline-2 focus-visible:outline-sky-400';

/** Fixed top bar: clear over the hero, frosted glass once the page scrolls under it. */
export function LandingNav() {
  const { primary, secondary } = useLandingCtas();
  const { scrollY } = useScroll();
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useMotionValueEvent(scrollY, 'change', (y) => setScrolled(y > 24));

  function handleKeyDown(event: KeyboardEvent) {
    if (event.key === 'Escape') setOpen(false);
  }

  return (
    <header
      onKeyDown={handleKeyDown}
      className={`fixed inset-x-0 top-0 z-50 border-b transition-[background-color,border-color,backdrop-filter] duration-300 ${
        scrolled || open
          ? 'border-white/[0.07] bg-slate-950/75 backdrop-blur-xl'
          : 'border-transparent bg-transparent'
      }`}
    >
      <nav
        aria-label="Primary"
        className="mx-auto flex h-16 max-w-6xl items-center gap-2 px-4 sm:gap-4 sm:px-6"
      >
        <Link to="/" aria-label="AIMIx home" className="shrink-0">
          <img src="/logo.png" alt="" className="h-10 w-auto" />
        </Link>
        {/* Hidden under 360px: four items do not fit there, and the footer carries the label. */}
        <span className="-ml-2 shrink-0 max-[359px]:hidden rounded-full border border-purple-400/30 bg-purple-400/10 px-2 py-0.5 text-[0.65rem] font-semibold tracking-wide text-purple-200 uppercase">
          {RELEASE_STAGE}
        </span>
        <ul className="ml-6 hidden items-center gap-1 lg:flex">
          {NAV_LINKS.map((link) => (
            <li key={link.href}>
              <a href={link.href} className={LINK}>
                {link.label}
              </a>
            </li>
          ))}
        </ul>
        <div className="ml-auto flex items-center gap-1.5 sm:gap-2">
          <GhostLink to={secondary.to} size="sm" className="whitespace-nowrap max-sm:px-3">
            {secondary.label}
          </GhostLink>
          <Link
            to={primary.to}
            className={glowButtonClass(
              'sm',
              'w-auto! whitespace-nowrap max-sm:px-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400',
            )}
          >
            {primary.label}
          </Link>
          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            aria-expanded={open}
            aria-controls="landing-menu"
            aria-label={open ? 'Close menu' : 'Open menu'}
            className="inline-flex size-10 cursor-pointer items-center justify-center rounded-lg text-slate-200 hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-sky-400 lg:hidden"
          >
            {open ? (
              <X aria-hidden="true" className="size-5" />
            ) : (
              <Menu aria-hidden="true" className="size-5" />
            )}
          </button>
        </div>
      </nav>
      <AnimatePresence>
        {open && (
          <motion.ul
            id="landing-menu"
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.18 }}
            className="mx-auto flex max-w-6xl flex-col gap-1 px-4 pb-4 lg:hidden"
          >
            {NAV_LINKS.map((link) => (
              <li key={link.href}>
                <a href={link.href} onClick={() => setOpen(false)} className={`${LINK} block py-3`}>
                  {link.label}
                </a>
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </header>
  );
}
