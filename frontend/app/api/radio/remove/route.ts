import { NextRequest, NextResponse } from 'next/server';
import { requireCaller, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders, backendErrorMessage } from '@/lib/backend';

export async function POST(request: NextRequest) {
  try {
    // Any signed-in user may reach this: a listener can remove a song they added
    // themselves (ACCT-05). Whether *this* song is theirs is the backend's call,
    // made against the queue's own attribution (ACCT-04, RAD-13) — which is why the
    // caller's real role and id are forwarded rather than a constant 'editor'.
    const { user, role } = await requireCaller(UserRole.LISTENER);

    const body = await request.json();
    const { song_id } = body;

    if (!song_id) {
      return NextResponse.json(
        { error: 'song_id is required' },
        { status: 400 }
      );
    }

    const response = await fetch(`${process.env.AGENT_API_URL}/api/radio/queue/remove`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...backendAuthHeaders(role, user.sub),
      },
      body: JSON.stringify({ song_id }),
    });

    // A refusal now has a reason worth reading — "you can only remove songs you
    // added yourself" — so the status and the backend's own wording are forwarded
    // instead of being flattened into a generic 500 (RAD-09, PLAT-07).
    if (!response.ok) {
      const errorBody = await response.json().catch(() => null);
      return NextResponse.json(
        {
          error:
            backendErrorMessage(errorBody) || `Backend API error: ${response.statusText}`,
        },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Remove from queue error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
