'use client';

import { useAuth } from '@/lib/useAuth';

export default function UserButton() {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="flex items-center gap-2">
        <div className="w-8 h-8 rounded-full bg-gray-300 animate-pulse"></div>
      </div>
    );
  }

  if (!user) {
    return (
      <a
        href="/api/auth/login"
        className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
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
        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
          {user.name}
        </span>
      </div>
      <a
        href="/api/auth/logout"
        className="px-3 py-1 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 border border-gray-300 dark:border-gray-600 rounded-lg hover:border-gray-400 transition"
      >
        Sign Out
      </a>
    </div>
  );
}
