import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// Beat times for the waveform beat markers (issue #70, reuses #69). Degrades
// gracefully backend-side: an empty list rather than an error when beats can't
// be detected.
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ songId: string }> }
) {
  try {
    await requireAuth(UserRole.EDITOR);
    const { songId } = await params;

    const sourceVersionId = request.nextUrl.searchParams.get('source_version_id');
    const query = sourceVersionId
      ? `?source_version_id=${encodeURIComponent(sourceVersionId)}`
      : '';

    const response = await fetch(
      `${AGENT_API_URL}/api/produce/songs/${songId}/beats${query}`,
      {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          ...backendAuthHeaders('editor'),
        },
      }
    );

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || 'Failed to load beats', beats: [] },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Produce beats error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error', beats: [] },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
