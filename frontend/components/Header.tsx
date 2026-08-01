'use client';

import Link from 'next/link';
import UserButton from './UserButton';
import { useAuth } from '@/lib/useAuth';

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

  // Check if user has editor or admin role
  const canEdit = user?.role === 'editor' || user?.role === 'admin';
  const canAdmin = user?.role === 'admin';

  return (
    <header className="bg-canvas text-text border-b border-white/8">
      <div className="container mx-auto px-4 py-4">
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-8">
            <Link href="/" className="hover:opacity-80 transition-opacity">
              <h1 className="text-3xl font-bold tracking-tight">{title}</h1>
              <p className="text-text/40 text-sm">{subtitle}</p>
            </Link>

            {showNav && (
              <nav className="hidden md:flex gap-1">
                <Link
                  href="/search"
                  className="text-text/50 hover:text-text hover:bg-white/8 transition-colors px-3 py-1.5 rounded-md text-sm font-medium"
                >
                  Search
                </Link>
                <Link
                  href="/radio"
                  className="text-text/50 hover:text-text hover:bg-white/8 transition-colors px-3 py-1.5 rounded-md text-sm font-medium"
                >
                  Radio
                </Link>
                {canEdit && (
                  <Link
                    href="/edit"
                    className="text-text/50 hover:text-text hover:bg-white/8 transition-colors px-3 py-1.5 rounded-md text-sm font-medium"
                  >
                    Edit
                  </Link>
                )}
                {canEdit && (
                  <Link
                    href="/produce"
                    className="text-text/50 hover:text-text hover:bg-white/8 transition-colors px-3 py-1.5 rounded-md text-sm font-medium"
                  >
                    Produce
                  </Link>
                )}
                {canAdmin && (
                  <Link
                    href="/admin"
                    className="text-text/50 hover:text-text hover:bg-white/8 transition-colors px-3 py-1.5 rounded-md text-sm font-medium"
                  >
                    Admin
                  </Link>
                )}
              </nav>
            )}
          </div>

          <UserButton />
        </div>
      </div>
    </header>
  );
}
