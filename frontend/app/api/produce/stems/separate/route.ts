import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// Start a background Demucs stem-separation job for a song (optionally a
// specific version's audio). Returns immediately with the queued stem set; the
// mixer polls GET /api/produce/songs/{id}/stems for the job's status.
export async function POST(request: NextRequest) {
  try {
    await requireAuth(UserRole.EDITOR);

    const body = await request.json().catch(() => ({}));
    if (typeof body?.song_id !== 'number') {
      return NextResponse.json({ error: 'song_id is required' }, { status: 400 });
    }

    const response = await fetch(`${AGENT_API_URL}/api/produce/stems/separate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...backendAuthHeaders('editor'),
      },
      body: JSON.stringify({
        song_id: body.song_id,
        ...(typeof body.source_version_id === 'number'
          ? { source_version_id: body.source_version_id }
          : {}),
      }),
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || 'Failed to start stem separation' },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Stem separate error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
