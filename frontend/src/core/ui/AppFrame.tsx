import { LogOut, Menu, X } from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode, type Ref } from 'react';
import { useLocation } from 'react-router-dom';

import { useMediaQuery } from '../hooks/useMediaQuery';
import { SidebarNav, type NavGroup } from './SidebarNav';

/** From this width (Tailwind's `lg`) the sidebar is always shown; below it, a menu opens it. */
const SIDEBAR_LAYOUT = '(min-width: 1024px)';
const MENU_ID = 'app-menu';
const SLIDE = { duration: 0.25, ease: [0.16, 1, 0.3, 1] } as const;
const FOCUS_RING =
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400';

function Logo() {
  return <img src="/logo.png" alt="AIMIx" className="h-9 w-auto" />;
}

interface SidebarBodyProps {
  groups: readonly NavGroup[];
  pillId: string;
  onLogout: () => void;
}

/** The sections, then Log out at the foot: the same in the sidebar and in the phone menu. */
function SidebarBody({ groups, pillId, onLogout }: SidebarBodyProps) {
  return (
    <div className="flex min-h-0 flex-1 flex-col justify-between gap-6 overflow-y-auto px-3 pt-2 pb-4">
      <SidebarNav groups={groups} pillId={pillId} />
      <button
        type="button"
        onClick={onLogout}
        className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-slate-400 transition-colors hover:bg-white/[0.04] hover:text-slate-50 ${FOCUS_RING}`}
      >
        <LogOut aria-hidden="true" className="size-4" />
        Log out
      </button>
    </div>
  );
}

interface MenuDrawerProps extends SidebarBodyProps {
  closeRef: Ref<HTMLButtonElement>;
  onClose: () => void;
}

/** The phone menu: the sidebar sliding in over a dimmed screen; Escape or a tap outside closes it. */
function MenuDrawer({ closeRef, onClose, ...body }: MenuDrawerProps) {
  function handleKeyDown(event: KeyboardEvent) {
    if (event.key === 'Escape') onClose();
  }
  return (
    <div className="fixed inset-0 z-50" onKeyDown={handleKeyDown}>
      <motion.div
        aria-hidden="true"
        onClick={onClose}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="absolute inset-0 bg-slate-950/70 backdrop-blur-sm"
      />
      <motion.div
        id={MENU_ID}
        role="dialog"
        aria-modal="true"
        aria-label="Menu"
        initial={{ x: '-100%' }}
        animate={{ x: 0 }}
        exit={{ x: '-100%' }}
        transition={SLIDE}
        className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col border-r border-white/[0.08] bg-slate-950"
      >
        <div className="flex h-[60px] shrink-0 items-center justify-between px-4">
          <Logo />
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label="Close menu"
            className={`rounded-lg p-2 text-slate-300 transition-colors hover:bg-white/5 hover:text-slate-50 ${FOCUS_RING}`}
          >
            <X aria-hidden="true" className="size-5" />
          </button>
        </div>
        <SidebarBody {...body} />
      </motion.div>
    </div>
  );
}

/**
 * The phone menu's state. It belongs to the page it was opened on, so following one of
 * its links closes it; it never counts as open once the window is wide enough for the
 * sidebar. Opening it moves focus to its Close button, closing it hands focus back.
 */
function useMenu() {
  const { pathname } = useLocation();
  const wide = useMediaQuery(SIDEBAR_LAYOUT);
  const [openOn, setOpenOn] = useState<string | null>(null);
  const open = !wide && openOn === pathname;
  const menuRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const wasOpen = useRef(false);

  useEffect(() => {
    if (open) closeRef.current?.focus();
    else if (wasOpen.current) menuRef.current?.focus();
    wasOpen.current = open;
  }, [open]);

  return {
    open,
    menuRef,
    closeRef,
    show: () => setOpenOn(pathname),
    close: () => setOpenOn(null),
  };
}

/** Below `lg`: the logo and the button that opens the menu. */
function TopBar({ menu }: { menu: ReturnType<typeof useMenu> }) {
  return (
    <header
      inert={menu.open}
      className="fixed inset-x-0 top-0 z-40 flex h-[60px] items-center justify-between border-b border-white/[0.06] bg-slate-950/70 px-4 backdrop-blur-xl lg:hidden"
    >
      <Logo />
      <button
        ref={menu.menuRef}
        type="button"
        onClick={menu.show}
        aria-label="Open menu"
        aria-expanded={menu.open}
        aria-controls={menu.open ? MENU_ID : undefined}
        className={`rounded-lg p-2 text-slate-300 transition-colors hover:bg-white/5 hover:text-slate-50 ${FOCUS_RING}`}
      >
        <Menu aria-hidden="true" className="size-5" />
      </button>
    </header>
  );
}

interface AppFrameProps {
  groups: readonly NavGroup[];
  onLogout: () => void;
  children: ReactNode;
}

/**
 * The signed-in screens' frame: a fixed sidebar with every section from `lg` up; below
 * it, a 60px top bar whose menu button opens the same sidebar as a drawer. The screen
 * itself is inert while the drawer is open.
 */
export function AppFrame({ groups, onLogout, children }: AppFrameProps) {
  const menu = useMenu();
  return (
    <>
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-56 flex-col border-r border-white/[0.06] bg-slate-950/70 backdrop-blur-xl lg:flex">
        <div className="flex h-16 shrink-0 items-center px-6">
          <Logo />
        </div>
        <SidebarBody groups={groups} pillId="app-nav" onLogout={onLogout} />
        {/* Hairline in the brand gradient along the right edge. */}
        <span
          aria-hidden="true"
          className="absolute inset-y-0 -right-px w-px bg-gradient-to-b from-transparent via-indigo-400/50 to-transparent"
        />
      </aside>
      <TopBar menu={menu} />
      <AnimatePresence>
        {menu.open && (
          <MenuDrawer
            groups={groups}
            pillId="app-nav-menu"
            onLogout={onLogout}
            closeRef={menu.closeRef}
            onClose={menu.close}
          />
        )}
      </AnimatePresence>
      <div inert={menu.open} className="pt-[60px] lg:pt-0 lg:pl-56">
        {children}
      </div>
    </>
  );
}
