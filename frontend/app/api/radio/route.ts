import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';

// GET /api/radio - Get current radio state (all users)
export async function GET(request: NextRequest) {
  try {
    // All authenticated users can listen
    await requireAuth(UserRole.LISTENER);

    // Pass listener_id if provided
    const { searchParams } = new URL(request.url);
    const listenerId = searchParams.get('listener_id');
    const url = listenerId
      ? `${process.env.AGENT_API_URL}/api/radio/state?listener_id=${listenerId}`
      : `${process.env.AGENT_API_URL}/api/radio/state`;

    const response = await fetch(url);

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
    await requireAuth(UserRole.LISTENER);

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
