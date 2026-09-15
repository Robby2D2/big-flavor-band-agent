import { previewInvite } from '@/lib/invites';
import InviteCard from '../InviteCard';

/** Always resolve the token against the live invite, never a cached render. */
export const dynamic = 'force-dynamic';

const UNUSABLE: Record<string, string> = {
  revoked: 'This invite has been revoked. Ask for a new one.',
  redeemed: 'This invite has already been used. If that was not you, ask for a new one.',
  expired: 'This invite has expired. Ask for a new one.',
};

export default async function InvitePage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  const invite = await previewInvite(token);

  if (!invite) {
    return (
      <InviteCard tone="error" heading="Invite not found">
        This link is not valid. Check that you copied the whole thing, or ask for a new invite.
      </InviteCard>
    );
  }

  if (invite.status !== 'valid') {
    return (
      <InviteCard tone="error" heading="This invite cannot be used">
        {UNUSABLE[invite.status]}
      </InviteCard>
    );
  }

  const expires = new Date(invite.expires_at).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });

  return (
    <InviteCard heading="You have been invited">
      <p>
        You have been invited to join the Big Flavor catalog as{' '}
        <strong className="text-text">{invite.role}</strong>.
      </p>
      <p className="mt-4">
        Sign in with Google as <strong className="text-text">{invite.email}</strong> — the invite
        only works for that address.
      </p>
      <a
        href={`/api/auth/login?invite=${encodeURIComponent(token)}`}
        className="mt-6 inline-block px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
      >
        Sign in with Google
      </a>
      <p className="mt-4 text-xs text-text/45">This invite expires on {expires}.</p>
    </InviteCard>
  );
}
