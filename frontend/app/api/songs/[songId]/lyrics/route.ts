import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// Plain lyrics for the "view lyrics" modal on the search/song list.
//
// Listener-scoped, like its /lyrics/timed sibling: the editor-facing lyric
// routes live under /api/produce/*, but any listener can read the words. Only
// /api/agent/* is proxied by next.config rewrites, so every other backend path
// the browser calls needs a route handler here — without this file the fetch in
// SongList resolved to nothing and the modal always said "Lyrics not found".
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ songId: string }> }
) {
  try {
    await requireAuth(UserRole.LISTENER);

    const { songId } = await params;

    const backendUrl = `${AGENT_API_URL}/api/songs/${songId}/lyrics`;
    const response = await fetch(backendUrl, { method: 'GET' });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || 'Failed to load lyrics' },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Lyrics error:', error);

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
