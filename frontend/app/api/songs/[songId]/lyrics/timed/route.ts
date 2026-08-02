import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// Lyrics + per-line timings for follow-along highlighting during playback.
// Listener-scoped (the editor-facing lyric routes live under /api/produce/*),
// since every listener's player reads this.
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ songId: string }> }
) {
  try {
    await requireAuth(UserRole.LISTENER);

    const { songId } = await params;

    const backendUrl = `${AGENT_API_URL}/api/songs/${songId}/lyrics/timed`;
    const response = await fetch(backendUrl, { method: 'GET' });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || 'Failed to load timed lyrics' },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Timed lyrics error:', error);

    if (error.message?.startsWith('Unauthorized')) {
      return NextResponse.json(
        { error: 'Please log in to view lyrics.' },
        { status: 401 }
      );
    }
    if (error.message?.startsWith('Forbidden')) {
      return NextResponse.json({ error: error.message }, { status: 403 });
    }

    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: 500 }
    );
  }
}
