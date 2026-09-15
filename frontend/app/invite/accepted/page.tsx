import InviteCard from '../InviteCard';

/**
 * Where the auth callback lands an invitee after it has tried to redeem their
 * invite — the only place the outcome of that redemption is reported.
 */
export default async function InviteAcceptedPage({
  searchParams,
}: {
  searchParams: Promise<{ role?: string; error?: string }>;
}) {
  const { role, error } = await searchParams;

  if (error || !role) {
    return (
      <InviteCard tone="error" heading="Invite not accepted">
        <p>{error || 'This invite could not be used.'}</p>
        <p className="mt-4 text-sm">
          You are signed in, but your role has not changed. Ask for a new invite.
        </p>
      </InviteCard>
    );
  }

  return (
    <InviteCard tone="success" heading="You are in">
      <p>
        Your account now has the <strong className="text-text">{role}</strong> role.
      </p>
      <p className="mt-4 text-sm">
        Editors can search and play the catalog, and use the audio production tools.
      </p>
    </InviteCard>
  );
}
