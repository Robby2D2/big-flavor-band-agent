import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// A song's stem sets (with job status) and each set's stems, for the stem
// mixer (issue #70). Rendering existing stems only — starting separation is
// out of this issue's scope.
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ songId: string }> }
) {
  try {
    await requireAuth(UserRole.EDITOR);
    const { songId } = await params;

    const response = await fetch(
      `${AGENT_API_URL}/api/produce/songs/${songId}/stems`,
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
        { error: data.detail || 'Failed to load stems', stem_sets: [] },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Produce stems error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error', stem_sets: [] },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
