'use client';

/** The console's in-place "working on it" indicator, sized by its caller. */
export default function Spinner({ className = '' }: { className?: string }) {
  return (
    <span
      className={`inline-block rounded-full border-2 border-signal/25 border-t-signal animate-spin ${className}`}
    />
  );
}
