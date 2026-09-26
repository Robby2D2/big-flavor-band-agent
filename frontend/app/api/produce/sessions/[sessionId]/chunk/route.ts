import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// One piece of a session upload.
//
// A session zip is multiple gigabytes, while nginx caps a body at 100 MB with a
// 60s read timeout, so the browser slices the file and sends it a chunk at a
// time. Each chunk is small enough to pass through this proxy comfortably, and
// `offset` makes a retry rewrite the same bytes rather than append them twice.
export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> }
) {
  try {
    await requireAuth(UserRole.EDITOR);
    const { sessionId } = await params;
    const offset = request.nextUrl.searchParams.get('offset') ?? '0';

    const body = await request.arrayBuffer();

    const response = await fetch(
      `${AGENT_API_URL}/api/produce/sessions/${sessionId}/chunk?offset=${offset}`,
      {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/octet-stream',
          ...backendAuthHeaders('editor'),
        },
        body,
      }
    );

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || 'Upload chunk failed' },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Session chunk error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
