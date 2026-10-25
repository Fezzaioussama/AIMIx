import {
  FolderOpen,
  LayoutGrid,
  MessageSquare,
  Rocket,
  Settings,
  Workflow,
  type LucideIcon,
} from 'lucide-react';

import { HOME_PATH } from '../routes';

/** The top bar's icon for each section: on a phone it sits above the section's name. */
const NAV_ICONS: Readonly<Record<string, LucideIcon>> = {
  [HOME_PATH]: Rocket,
  '/chat': MessageSquare,
  '/pipeline': Workflow,
  '/files': FolderOpen,
  '/settings': Settings,
};

/** A section's icon; one added later without its own gets a generic icon. */
export function navIcon(to: string): LucideIcon {
  return NAV_ICONS[to] ?? LayoutGrid;
}
