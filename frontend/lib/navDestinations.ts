import type { User } from './useAuth';

export type NavDestination = {
  href: string;
  label: string;
  /** Omitted means every signed-in or anonymous visitor may see it. */
  requires?: 'edit' | 'admin';
};

/**
 * The single definition of where the header can take you. Both the desktop nav
 * and the mobile drawer render this, so a destination added here appears in
 * both with the same role rules.
 */
export const NAV_DESTINATIONS: NavDestination[] = [
  { href: '/search', label: 'Search' },
  { href: '/radio', label: 'Radio' },
  { href: '/edit', label: 'Edit', requires: 'edit' },
  { href: '/produce', label: 'Produce', requires: 'edit' },
  { href: '/admin', label: 'Admin', requires: 'admin' },
];

export function visibleDestinations(role: User['role']): NavDestination[] {
  const canEdit = role === 'editor' || role === 'admin';
  const canAdmin = role === 'admin';

  return NAV_DESTINATIONS.filter((destination) => {
    if (destination.requires === 'admin') return canAdmin;
    if (destination.requires === 'edit') return canEdit;
    return true;
  });
}
