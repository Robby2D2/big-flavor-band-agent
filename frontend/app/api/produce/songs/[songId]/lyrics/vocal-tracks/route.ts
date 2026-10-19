import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// List the stems lyric extraction can transcribe, with the default picks marked.
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ songId: string }> }
) {
  try {
    await requireAuth(UserRole.EDITOR);
    const { songId } = await params;

    const response = await fetch(
      `${AGENT_API_URL}/api/produce/songs/${songId}/lyrics/vocal-tracks`,
      { method: 'GET', headers: { 'Content-Type': 'application/json', ...backendAuthHeaders('editor') } }
    );
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json({ error: data.detail || 'Failed to load vocal tracks' }, { status: response.status });
    }
    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Get vocal tracks error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
