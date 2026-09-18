'use client';

import { useAuth } from '@/lib/useAuth';

export default function UserButton() {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="flex items-center gap-2">
        <div className="w-8 h-8 rounded-full bg-white/10 animate-pulse"></div>
      </div>
    );
  }

  if (!user) {
    // A real navigation, not a client-side route change: /api/auth/* are route
    // handlers that redirect to Google's consent screen, which next/link cannot
    // do. The rule can't tell a route handler from a page.
    return (
      // eslint-disable-next-line @next/next/no-html-link-for-pages
      <a
        href="/api/auth/login"
        className="px-4 py-2 bg-signal text-canvas font-semibold rounded-lg hover:opacity-90 transition"
      >
        Sign In with Google
      </a>
    );
  }

  return (
    <div className="flex items-center gap-3">
      <div className="flex items-center gap-2">
        {user.picture && (
          // Same as the admin table's avatar: a 32px external image is not
          // worth a remotePatterns entry and the optimizer.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={user.picture}
            alt={user.name || 'User'}
            className="w-8 h-8 rounded-full"
          />
        )}
        <span className="text-sm font-medium text-text/70">
          {user.name}
        </span>
      </div>
      {/* Same as the sign-in link above: a server redirect, not a page. */}
      {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
      <a
        href="/api/auth/logout"
        className="px-3 py-1 text-sm text-text/60 hover:text-text border border-white/14 rounded-lg hover:border-white/25 transition"
      >
        Sign Out
      </a>
    </div>
  );
}
