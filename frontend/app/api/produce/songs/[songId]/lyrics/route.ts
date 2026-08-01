import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// Fetch a song's stored lyrics.
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ songId: string }> }
) {
  try {
    await requireAuth(UserRole.EDITOR);
    const { songId } = await params;

    const response = await fetch(
      `${AGENT_API_URL}/api/produce/songs/${songId}/lyrics`,
      { method: 'GET', headers: { 'Content-Type': 'application/json', ...backendAuthHeaders('editor') } }
    );
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json({ error: data.detail || 'Failed to load lyrics' }, { status: response.status });
    }
    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Get lyrics error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}

// Save hand-edited lyrics.
export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ songId: string }> }
) {
  try {
    await requireAuth(UserRole.EDITOR);
    const { songId } = await params;
    const body = await request.json();

    const response = await fetch(
      `${AGENT_API_URL}/api/produce/songs/${songId}/lyrics`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...backendAuthHeaders('editor') },
        body: JSON.stringify({ lyrics: body.lyrics ?? '' }),
      }
    );
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json({ error: data.detail || 'Failed to save lyrics' }, { status: response.status });
    }
    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Save lyrics error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
