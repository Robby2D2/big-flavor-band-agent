'use client';

import Link from 'next/link';
import UserButton from './UserButton';
import MobileNav from './MobileNav';
import { useAuth } from '@/lib/useAuth';
import { visibleDestinations } from '@/lib/navDestinations';

interface HeaderProps {
  title?: string;
  subtitle?: string;
  showNav?: boolean;
}

export default function Header({
  title = 'BigFlavor Band Agent',
  subtitle = 'Discover 1,415+ songs powered by AI',
  showNav = true
}: HeaderProps) {
  const { user } = useAuth();

  const destinations = visibleDestinations(user?.role);

  return (
    <header className="bg-canvas text-text border-b border-white/8">
      <div className="container relative mx-auto px-4 py-4">
        <div className="flex justify-between items-center gap-2">
          <div className="flex min-w-0 items-center gap-8">
            <Link href="/" className="min-w-0 hover:opacity-80 transition-opacity">
              <h1 className="truncate text-xl sm:text-3xl font-bold tracking-tight">{title}</h1>
              <p className="hidden sm:block text-text/40 text-sm">{subtitle}</p>
            </Link>

            {showNav && (
              <nav className="hidden md:flex gap-1">
                {destinations.map(({ href, label }) => (
                  <Link
                    key={href}
                    href={href}
                    className="text-text/50 hover:text-text hover:bg-white/8 transition-colors px-3 py-1.5 rounded-md text-sm font-medium"
                  >
                    {label}
                  </Link>
                ))}
              </nav>
            )}
          </div>

          <div className="flex shrink-0 items-center gap-1">
            <UserButton />
            {showNav && <MobileNav destinations={destinations} />}
          </div>
        </div>
      </div>
    </header>
  );
}
