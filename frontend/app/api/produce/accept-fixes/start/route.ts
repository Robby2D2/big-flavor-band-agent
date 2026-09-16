import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// Start a whole-queue render in the background and return at once.
//
// Rendering seventeen fixes across six stems takes minutes, which is longer
// than the edge proxy will hold a request open — the synchronous route came
// back as a 504 and the UI could only suggest turning fixes off. The backend
// answers immediately here; the page polls the status route for the outcome.
// An unchanged fix set that was already rendered comes back complete straight
// away, without rendering anything again.
export async function POST(request: NextRequest) {
  try {
    await requireAuth(UserRole.EDITOR);

    const body = await request.json();
    if (body?.song_id == null) {
      return NextResponse.json({ error: 'song_id is required' }, { status: 400 });
    }

    const response = await fetch(`${AGENT_API_URL}/api/produce/accept-fixes/start`, {
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
        { error: data.detail || 'Could not start the render' },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Start accept-fixes error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
