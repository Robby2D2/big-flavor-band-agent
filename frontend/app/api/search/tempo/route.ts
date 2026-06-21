import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

export async function POST(request: NextRequest) {
  try {
    await requireAuth(UserRole.LISTENER);

    const body = await request.json().catch(() => ({}));
    const { min_bpm = null, max_bpm = null, limit = 20 } = body;

    const response = await fetch(`${AGENT_API_URL}/api/search/tempo`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ min_bpm, max_bpm, limit }),
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || 'Tempo search failed' },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Tempo search error:', error);

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
