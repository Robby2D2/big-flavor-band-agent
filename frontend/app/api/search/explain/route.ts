import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// "Why did this match?" for one song, asked only when a listener clicks the (i).
// This is the one LLM call left anywhere near search — it used to run for every
// result of every search, which is what made searching take seconds.
export async function POST(request: NextRequest) {
  try {
    await requireAuth(UserRole.LISTENER);

    const body = await request.json().catch(() => ({}));
    const { query, song_id } = body;

    if (!query || !song_id) {
      return NextResponse.json(
        { error: 'query and song_id are required' },
        { status: 400 }
      );
    }

    const response = await fetch(`${AGENT_API_URL}/api/search/explain`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, song_id }),
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || 'Could not explain this match' },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Explain match error:', error);

    if (error.message?.startsWith('Unauthorized')) {
      return NextResponse.json(
        { error: 'Please log in to search songs.' },
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
