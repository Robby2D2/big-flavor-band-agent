import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

export async function POST(request: NextRequest) {
  try {
    await requireAuth(UserRole.EDITOR);

    const body = await request.json();
    if (body?.song_id == null) {
      return NextResponse.json({ error: 'song_id is required' }, { status: 400 });
    }

    const response = await fetch(`${process.env.AGENT_API_URL}/api/produce/auto-clean`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...backendAuthHeaders('editor'),
      },
      body: JSON.stringify({
        song_id: body.song_id,
        aggressiveness: body.aggressiveness || 'moderate',
        steps_override: body.steps_override ?? null,
      }),
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || 'Auto-clean failed' },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Produce auto-clean error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
