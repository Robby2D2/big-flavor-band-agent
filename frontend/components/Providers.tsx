'use client';

// Auth0 UserProvider is no longer needed in newer versions
export default function Providers({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
