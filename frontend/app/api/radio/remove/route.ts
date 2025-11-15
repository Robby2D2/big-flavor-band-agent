import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';

export async function POST(request: NextRequest) {
  try {
    // Require editor role
    await requireAuth(UserRole.EDITOR);

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
      },
      body: JSON.stringify({ song_id }),
    });

    if (!response.ok) {
      throw new Error(`Backend API error: ${response.statusText}`);
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
