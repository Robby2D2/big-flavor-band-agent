import { NextRequest, NextResponse } from 'next/server';
import { requireCaller, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

// GET /api/radio - Get current radio state (all users)
export async function GET(request: NextRequest) {
  try {
    // All authenticated users can listen
    const { user, role } = await requireCaller(UserRole.LISTENER);

    // Pass listener_id if provided
    const { searchParams } = new URL(request.url);
    const listenerId = searchParams.get('listener_id');
    const url = listenerId
      ? `${process.env.AGENT_API_URL}/api/radio/state?listener_id=${listenerId}`
      : `${process.env.AGENT_API_URL}/api/radio/state`;

    // The caller's identity goes with the read so each queue entry can come back
    // saying whether *this* user added it — which is what decides whether they are
    // offered a remove control for it (ACCT-15, RAD-13).
    const response = await fetch(url, { headers: backendAuthHeaders(role, user.sub) });

    if (!response.ok) {
      throw new Error(`Backend API error: ${response.statusText}`);
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Radio state error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Unauthorized') ? 401 : 500 }
    );
  }
}

// POST /api/radio - Add songs to queue (all authenticated users)
export async function POST(request: NextRequest) {
  try {
    // All authenticated users can request songs
    const { user, role } = await requireCaller(UserRole.LISTENER);

    const body = await request.json();
    const { message } = body;

    if (!message) {
      return NextResponse.json(
        { error: 'message is required' },
        { status: 400 }
      );
    }

    const response = await fetch(`${process.env.AGENT_API_URL}/api/radio/queue/add`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        // Who added a song is what later lets them take their own add back without
        // needing an editor (ACCT-05, RAD-13).
        ...backendAuthHeaders(role, user.sub),
      },
      body: JSON.stringify({ message }),
    });

    if (!response.ok) {
      throw new Error(`Backend API error: ${response.statusText}`);
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Add to queue error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Unauthorized') ? 401 : 500 }
    );
  }
}
