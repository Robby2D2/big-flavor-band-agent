import { ReactNode } from 'react';
import Link from 'next/link';

/** The single centered card every invite page renders into. */
export default function InviteCard({
  heading,
  children,
  tone = 'neutral',
}: {
  heading: string;
  children: ReactNode;
  tone?: 'neutral' | 'error' | 'success';
}) {
  const headingColor =
    tone === 'error'
      ? 'text-red-600 dark:text-red-400'
      : tone === 'success'
        ? 'text-green-600 dark:text-green-400'
        : 'text-text';

  return (
    <div className="min-h-screen bg-canvas flex items-center justify-center px-4">
      <div className="max-w-md w-full bg-panel rounded-lg shadow-lg p-8 text-center">
        <h1 className={`text-2xl font-bold mb-4 ${headingColor}`}>{heading}</h1>
        <div className="text-text/55">{children}</div>
        <Link href="/" className="mt-6 inline-block text-sm text-text/45 hover:text-text">
          Back to Home
        </Link>
      </div>
    </div>
  );
}
