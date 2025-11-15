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
    <header className="bg-gray-900 text-white">
      <div className="container mx-auto px-4 py-4">
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-8">
            <Link href="/" className="hover:opacity-80 transition-opacity">
              <h1 className="text-3xl font-bold">{title}</h1>
              <p className="text-gray-400 text-sm">{subtitle}</p>
            </Link>

            {showNav && (
              <nav className="hidden md:flex gap-6">
                <Link
                  href="/search"
                  className="text-gray-300 hover:text-white transition-colors"
                >
                  Search
                </Link>
                <Link
                  href="/radio"
                  className="text-gray-300 hover:text-white transition-colors"
                >
                  Radio
                </Link>
                {canEdit && (
                  <Link
                    href="/edit"
                    className="text-gray-300 hover:text-white transition-colors"
                  >
                    Edit
                  </Link>
                )}
                {canAdmin && (
                  <Link
                    href="/admin"
                    className="text-gray-300 hover:text-white transition-colors"
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
