import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// Render every accepted per-stem + master fix into one file: "Preview full
// mix first" (preview: true) or "Accept all & save version" (preview: false,
// the default) in the review-queue UI.
export async function POST(request: NextRequest) {
  try {
    await requireAuth(UserRole.EDITOR);

    const body = await request.json();
    if (body?.song_id == null) {
      return NextResponse.json({ error: 'song_id is required' }, { status: 400 });
    }

    const response = await fetch(`${AGENT_API_URL}/api/produce/accept-fixes`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...backendAuthHeaders('editor'),
      },
      body: JSON.stringify({
        song_id: body.song_id,
        source_version_id: body.source_version_id ?? null,
        stems: body.stems ?? [],
        master_fixes: body.master_fixes ?? [],
        preview: body.preview ?? false,
      }),
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || 'Accept fixes failed' },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Accept fixes error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
