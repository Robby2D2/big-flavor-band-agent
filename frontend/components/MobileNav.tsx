'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import type { NavDestination } from '@/lib/navDestinations';

interface MobileNavProps {
  destinations: NavDestination[];
}

/**
 * The below-`md` replacement for the desktop nav: one toggle button and a
 * drawer over the header. Takes its destinations already role-filtered, so a
 * link the user may not use is absent from the DOM rather than hidden.
 */
export default function MobileNav({ destinations }: MobileNavProps) {
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    if (!isOpen) return;

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setIsOpen(false);
    }

    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [isOpen]);

  if (destinations.length === 0) return null;

  return (
    <div className="md:hidden">
      <button
        type="button"
        aria-label="Menu"
        aria-expanded={isOpen}
        aria-controls="mobile-nav"
        onClick={() => setIsOpen((open) => !open)}
        className="relative z-50 flex h-11 w-11 items-center justify-center rounded-md text-text/70 hover:text-text hover:bg-white/8 transition-colors"
      >
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          className="h-6 w-6"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
        >
          {isOpen ? (
            <path d="M6 6l12 12M18 6L6 18" />
          ) : (
            <path d="M4 7h16M4 12h16M4 17h16" />
          )}
        </svg>
      </button>

      {isOpen && (
        <>
          <div
            aria-hidden="true"
            onClick={() => setIsOpen(false)}
            className="fixed inset-0 z-40 bg-black/50"
          />
          <nav
            id="mobile-nav"
            className="absolute inset-x-0 top-full z-50 border-y border-white/8 bg-panel px-4 py-2 shadow-lg"
          >
            {destinations.map(({ href, label }) => (
              <Link
                key={href}
                href={href}
                onClick={() => setIsOpen(false)}
                className="flex min-h-11 items-center rounded-md px-4 py-3 text-base font-medium text-text/70 hover:text-text hover:bg-white/8 transition-colors"
              >
                {label}
              </Link>
            ))}
          </nav>
        </>
      )}
    </div>
  );
}
