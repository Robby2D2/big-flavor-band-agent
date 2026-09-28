import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders, backendErrorMessage } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// Render the master fixes over a whole version, for the full-mix row. Cached
// per chain on the server, so pressing play twice renders it once.
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ versionId: string }> }
) {
  try {
    await requireAuth(UserRole.EDITOR);
    const { versionId } = await params;
    const body = await request.json().catch(() => ({}));

    const response = await fetch(
      `${AGENT_API_URL}/api/produce/versions/${encodeURIComponent(versionId)}/preview-chain`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...backendAuthHeaders('editor'),
        },
        body: JSON.stringify({ fixes: body?.fixes ?? [] }),
      }
    );

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json(
        { error: backendErrorMessage(data) || 'Preview chain failed' },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Version preview-chain error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
