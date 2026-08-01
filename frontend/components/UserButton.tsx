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
    return (
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
      <a
        href="/api/auth/logout"
        className="px-3 py-1 text-sm text-text/60 hover:text-text border border-white/14 rounded-lg hover:border-white/25 transition"
      >
        Sign Out
      </a>
    </div>
  );
}
