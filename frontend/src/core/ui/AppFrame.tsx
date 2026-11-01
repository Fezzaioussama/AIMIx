import { LogOut, Menu, UserRound, X } from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode, type Ref } from 'react';
import { Link, useLocation } from 'react-router-dom';

import { useMediaQuery } from '../hooks/useMediaQuery';
import { HOME_PATH } from '../routes';
import { FOCUS_RING } from './focus';
import { GradientText } from './reactbits/GradientText';
import { SidebarNav, type NavGroup } from './SidebarNav';

/** From this width (Tailwind's `lg`) the sidebar is always shown; below it, a menu opens it. */
const SIDEBAR_LAYOUT = '(min-width: 1024px)';
const MENU_ID = 'app-menu';
const SLIDE = { duration: 0.25, ease: [0.16, 1, 0.3, 1] } as const;

/** The logo and the wordmark, leading to Missions, the app's front door. */
function Brand() {
  return (
    <Link to={HOME_PATH} className={`flex items-center gap-2.5 rounded-lg ${FOCUS_RING}`}>
      <img src="/logo.png" alt="" className="h-10 w-auto" />
      <GradientText className="text-xl font-extrabold tracking-tight">AIMIx</GradientText>
    </Link>
  );
}

interface AccountProps {
  /** The signed-in username; null until it is known. */
  name: string | null;
  onLogout: () => void;
}

/** Who is signed in, with Log out beside the name. */
function AccountCard({ name, onLogout }: AccountProps) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-white/[0.06] bg-white/[0.03] p-2 pl-2.5">
      <span
        aria-hidden="true"
        className="grid size-8 shrink-0 place-items-center rounded-full bg-gradient-to-br from-sky-400 via-indigo-500 to-purple-500 text-sm font-semibold text-white uppercase"
      >
        {name ? name.charAt(0) : <UserRound className="size-4" />}
      </span>
      <p className="min-w-0 flex-1 truncate text-sm font-medium text-slate-200" title={name ?? ''}>
        <span className="sr-only">Signed in as </span>
        {name ?? 'Your account'}
      </p>
      <button
        type="button"
        onClick={onLogout}
        aria-label="Log out"
        title="Log out"
        className={`shrink-0 rounded-lg p-2 text-slate-400 transition-colors hover:bg-white/5 hover:text-slate-50 ${FOCUS_RING}`}
      >
        <LogOut aria-hidden="true" className="size-4" />
      </button>
    </div>
  );
}

interface SidebarBodyProps extends AccountProps {
  groups: readonly NavGroup[];
  pillId: string;
}

/**
 * The sections, scrolling when the window is short, then the account card pinned at the
 * foot: the same in the sidebar and in the phone menu.
 */
function SidebarBody({ groups, pillId, ...account }: SidebarBodyProps) {
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 px-3 pt-2 pb-3">
      <div className="min-h-0 flex-1 overflow-y-auto">
        <SidebarNav groups={groups} pillId={pillId} />
      </div>
      <AccountCard {...account} />
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
          <Brand />
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
      <Brand />
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

interface AppFrameProps extends AccountProps {
  groups: readonly NavGroup[];
  children: ReactNode;
}

/**
 * The signed-in screens' frame: a fixed sidebar with every section from `lg` up; below
 * it, a 60px top bar whose menu button opens the same sidebar as a drawer. The screen
 * itself is inert while the drawer is open.
 */
export function AppFrame({ groups, children, ...account }: AppFrameProps) {
  const menu = useMenu();
  return (
    <>
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-56 flex-col border-r border-white/[0.06] bg-slate-950/70 backdrop-blur-xl lg:flex">
        <div className="flex h-16 shrink-0 items-center px-5">
          <Brand />
        </div>
        <SidebarBody groups={groups} pillId="app-nav" {...account} />
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
            {...account}
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
